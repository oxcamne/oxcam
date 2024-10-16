"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are the implementation of the Stripe payment processor
interface
"""
from py4web import action, redirect, Field, request, URL
from .common import db, session, flash
from .models import primary_email, event_unpaid
from .controllers import checkaccess, form_style
from .utilities import notify_support, newpaiddate, msg_header, msg_send, event_confirm
from py4web.utils.form import Form
from .settings import CURRENCY_SYMBOL, PaymentProcessor, PAYMENTPROCESSORS, PAGE_BANNER, HOME_URL, HELP_URL
from yatl.helpers import H5, BEAUTIFY, CAT, XML
from py4web.utils.factories import Inject
import stripe, decimal, datetime, random

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL))

#locate named or default processor
def paymentprocessor(name=session.pay_source):
	return next((p for p in PAYMENTPROCESSORS if p.name==name)) if name else PAYMENTPROCESSORS[0]

def stripeprocessor():
	return next((p for p in PAYMENTPROCESSORS if p.name=='stripe'))

stripe.api_key = stripeprocessor().secret_key
stripe.api_version = '2023-10-16'

class StripeProcessor(PaymentProcessor):

	#get dues details for membership type
	def get_dues(self, membership):
		product = stripe.Product.retrieve(stripeprocessor().dues_products.get(membership))
		price = stripe.Price.retrieve(product.default_price)
		return decimal.Decimal(price.unit_amount)/100
	
	#update Stripe Customer Record with current primary email
	def update_email(self, member):
		if member.Pay_cust:
			try:	#check customer still exists on Stripe
				stripe.Customer.modify(member.Pay_cust, email=primary_email(member.id))
			except Exception as e:
				member.update_record(Pay_cust=None, Pay_subs=None, Pay_next=None)

	#process a Stripe transaction
	def process_charge(self, dict_csv, bank, reference, timestamp, amount, fee):
		acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first()
		actkts = db(db.CoA.Name.ilike("Ticket sales")).select().first()
		charge = stripe.Charge.retrieve(dict_csv['Source'])
		member = db(db.Members.Pay_cust==charge.customer).select().first()
		notes = f"{dict_csv['Source']}"
		if dict_csv['Type']=='charge':
			if (charge.description=='Subscription update' or (member.Charged and amount>=member.Charged)) and member.Membership:
				#dues paid, charge may also cover an event (auto renewal or manual)
				if (charge.description or '').startswith('Subscription'):
					subscription = stripe.Subscription.list(customer=charge.customer).data[0]
					notes += f' Subscription: {subscription.id}'
					member.update_record(Pay_next=datetime.datetime.fromtimestamp(subscription.current_period_end).date())
				product = stripe.Product.retrieve(self.dues_products[member.Membership])
				duesprice = stripe.Price.retrieve(product.default_price)
				duesamount = decimal.Decimal(duesprice.unit_amount)/100
				duesfee = (duesamount * fee)/amount	#prorate fee
				nowpaid = newpaiddate(member.Paiddate, timestamp=timestamp)
				db.AccTrans.insert(Bank = bank.id, Account = acdues.id, Amount = duesamount,
						Member=member.id, Paiddate=member.Paiddate, Membership=member.Membership,
						Fee = duesfee, Accrual = False, Timestamp = timestamp,
						Reference = reference, Notes = notes)
				member.update_record(Paiddate=nowpaid, Charged=None)
				fee -= duesfee
				amount -= duesamount

			if amount > 0:	#presumably apply to event reservations
				resvtn=db((db.Reservations.Member==member.id)&(db.Reservations.Charged>=amount)).select(
								orderby=db.Reservations.Modified).first()
				if resvtn:
					db.AccTrans.insert(Bank = bank.id, Account = actkts.id, Member=member.id, Amount = amount, Fee = fee,
						Timestamp = timestamp, Event = resvtn.Event, Reference = reference, Accrual = False, Notes = notes)
					resvtn.update_record(Charged = resvtn.Charged - amount, Checkout=None)
					amount = 0
		return (amount, notes)	#if amount not zero will be stored as unallocated

	def cancel_subscription(self, member):
		if member.Pay_subs:	#delete Stripe subscription if applicable
			try:
				stripe.Subscription.delete(member.Pay_subs)
			except Exception as e:
				pass
		return False

	#daily maintence for subscriptions
	def subscription_cancelled(self, member):	#return True if subscription no longer current
		product = stripe.Product.retrieve(self.dues_products[member.Membership])
		if member.Pay_subs:	#delete Stripe subscription if applicable
			try:
				subscription = stripe.Subscription.retrieve(member.Pay_subs)

				if subscription.plan.id!=product.default_price:
					#dues payment to change with next renewal but not retroactively
					stripe.SubscriptionItem.modify(subscription['items'].data[0].id, price=product.default_price, proration_behavior='none')

				if not subscription.canceled_at:
					return False		#canceled_at set when last payment 	attempt fails
				#note after auto-pay fails and cancels the subsription, it can no longer be deleted from Stripe
			except Exception as e:
				pass
		return True		#can't retrieve subscription

	def checkout(self, back):
		if not (session.member_id and (session.get('membership') or session.get('event_id'))):
			redirect(URL('index'))	#protect against regurgitated old requests

		member = db.Members[session.member_id]
		if member.Pay_cust:	#check customer still exists on Stripe
			try:
				customer = stripe.Customer.retrieve(member.Pay_cust)
			except Exception as e:
				member.update_record(Pay_cust=None, Pay_subs=None, Pay_source=None)
		
		mode = 'payment'
		items = []
		params = dict(member_id=member.id)	#for checkout_success
		event = None
		
		if member.Pay_cust:
			stripe.Customer.modify(member.Pay_cust, email=primary_email(member.id))	#in case has changed
		else:
			customer = stripe.Customer.create(email=primary_email(member.id))
			member.update_record(Pay_cust=customer.id, Pay_source='stripe')
		
		if session.get('membership'):	#this includes a membership subscription
			#get the subscription plan id (Full membership) or 1-year price (Student) from Stripe Products
			product = stripe.Product.retrieve(stripeprocessor().dues_products[session['membership']])
			price = stripe.Price.retrieve(product.default_price)
			params['dues'] = session.get('dues')
			params['membership'] = session.get('membership')
			if price.recurring:
				mode = 'subscription'
			items.append(dict(price = product.default_price, quantity = 1))
			
		if session.get('event_id'):			#event registration
			event = db.Events[session.get('event_id')]
			tickets_tbc = event_unpaid(event.id, member.id)
			if tickets_tbc:
				params['event_id'] = event.id
				params['tickets_tbc'] = tickets_tbc
				items.append({
					'price_data': {
						'currency': 'usd',
						'unit_amount': int(tickets_tbc*100),
						'product_data': {
							'name': 'Event Registration',
							'description': event.Description,
						},
					},
					'quantity': 1,
				}),

		token = str(random.randint(10000,999999))
		params['token'] = token
		session['token'] =token

		stripe_session = stripe.checkout.Session.create(
		customer=member.Pay_cust,
		payment_method_types=['card'], line_items=items, mode=mode,
		success_url=URL('stripe_checkout_success', vars=params, scheme=True),
		cancel_url=back
		)
		redirect(stripe_session.url)

	#display Stripe Checkout form to enter new card credentials
	def update_card(self, member):
		token = str(random.randint(10000,999999))
		session['token'] =token

		stripe_session = stripe.checkout.Session.create(
			payment_method_types=['card'],
			mode='setup',
			customer=member.Pay_cust,
			setup_intent_data={},
			success_url=URL('stripe_switched_card', vars=dict(token=token), scheme=True),
			cancel_url=URL('index', scheme=True)
		)
		redirect(stripe_session.url)
	
	def view_card(self):
		redirect(URL('stripe_view_card'))

@action('stripe_view_card', method=['GET', 'POST'])
@preferred
@checkaccess(None)
def stripe_view_card():
	access = session.access	#for layout.html

	if not session.member_id:
		redirect(URL('index'))
	member = db.Members[session.member_id]
	
	if member.Pay_subs and member.Pay_subs!='Cancelled':
		try:	#check subscription still exists on Stripe
			subscription = stripe.Subscription.retrieve(member.Pay_subs)
		except Exception as e:
			member.update_record(Pay_subs=None, Pay_next=None)
	if not (member.Pay_subs and member.Pay_subs!='Cancelled'):
		redirect(URL('index'))	#Stripe subscription doesn't exist
		
	paymentmethod = stripe.PaymentMethod.retrieve(subscription.default_payment_method)
	renewaldate = member.Pay_next.strftime('%b %d, %Y')
	duesamount = decimal.Decimal(subscription.plan.amount)/100
	header = CAT(H5('Membership Subscription'),
	      XML(f"Your next renewal payment of {CURRENCY_SYMBOL}{duesamount} will be charged to {paymentmethod.card.brand.capitalize()} \
....{paymentmethod.card.last4} exp {paymentmethod.card.exp_month}/{paymentmethod.card.exp_year} on {renewaldate}.<br><br>"))
	
	form = Form([], submit_value='Update Card on File')

	if form.accepted:
		stripeprocessor().update_card(member)	#redirects to Stripe
	return locals()

#new card successfully registered using checkout
@action('stripe_switched_card', method=['GET'])
@preferred
@checkaccess(None)
def stripe_switched_card():
	member = db.Members[session.member_id]

	if not request.query.token or request.query.token != session.token:
		raise Exception(f"Unexpected checkout_success callback received from Stripe, member {member.id}, event {session.get('event_id')}")
	
	payment_method = stripe.PaymentMethod.list(customer=member.Pay_cust).data[0]
	stripe.Customer.modify(member.Pay_cust, invoice_settings={'default_payment_method': payment_method.id})
	stripe.Subscription.modify(member.Pay_subs, default_payment_method=payment_method.id)
	flash.set('Thank you for updating your credit card information!')
	notify_support(member.id, 'Credit Card Update', 'Credit card updated.')
	redirect(URL('stripe_view_card'))

@action('stripe_checkout_success', method=['GET'])
@preferred
@checkaccess(None)
def stripe_checkout_success():
	member = db.Members[session.member_id]
	dues = decimal.Decimal(request.query.get('dues', 0))
	tickets_tbc = decimal.Decimal(request.query.get('tickets_tbc', 0))

	if not request.query.token or request.query.token != session.token:
		raise Exception(f"Unexpected checkout_success callback received from Stripe, member {member.id}, event {session.get('event_id')}")

	subject = 'Registration Confirmation' if tickets_tbc>0 else 'Thank you for your membership payment'
	message = f"{msg_header(member, subject)}<b>Received: {CURRENCY_SYMBOL}{dues+tickets_tbc}</b><br>"
	
	if dues>0:
		next = None
		subscriptions = stripe.Subscription.list(customer=member.Pay_cust)
		if subscriptions:
			subscription = subscriptions.data[0]
			next = datetime.datetime.fromtimestamp(subscription.current_period_end).date()
		member.update_record(Membership=request.query.get('membership'),
			Pay_subs=subscription.id, Pay_next=next, Charged=dues)
		message += 'Thank you, your membership is now current.</b><br>'
		
	if tickets_tbc>0:
		host_reservation = db((db.Reservations.Event==request.query.get('event_id'))&(db.Reservations.Member == member.id)\
					&(db.Reservations.Host == True)).select().first()
		message += '<br><b>Your registration is now confirmed:</b><br>'
		host_reservation.update_record(Charged = (host_reservation.Charged or 0) + tickets_tbc, Checkout = None)
		message +=event_confirm(request.query.get('event_id'), member.id, dues)

	msg_send(member,subject, message)
	
	flash.set('Thank you for your payment. Confirmation has been sent by email!')
	session['membership'] = None
	session['dues'] = None
	session['event_id'] = None
	session['stripe_session_id'] = None
	if dues:
		flash.set('Confirmation has been sent by email. Please review your mailing list subscriptions.')
		redirect(URL(f"emails/Y/{member.id}/select", vars=dict(back=URL('index'))))
		#it would be nice to go right to edit the subscription of the primary email,
		#but a side effect of Stripe Checkout seems to be that the first 'submit' doesn't work
		#I think this is CSRF protection at work.
		#redirect(URL(f"emails/Y/{member.id}/edit/{db(db.Emails.Member == member.id).select(orderby=~db.Emails.Modified).first().id}"))
	redirect(URL('index'))

#install implementation in base class
PAYMENTPROCESSORS = [StripeProcessor(
	p.name, p.public_key, p.secret_key, p.dues_products
) if p.name == 'stripe' else p for p in PAYMENTPROCESSORS]