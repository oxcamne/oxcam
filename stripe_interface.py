"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are the implementation of the Stripe payment processor
interface
"""
from py4web import action, redirect, Field, request, URL
from .common import db, session, flash
from .models import primary_email, member_name, res_tbc
from .controllers import checkaccess, form_style
from .utilities import notify_support, newpaiddate, msg_header, msg_send, event_confirm
from py4web.utils.form import Form
from .settings import STRIPE_SKEY, STRIPE_PKEY, SOCIETY_DOMAIN, STRIPE_EVENT, STRIPE_PROD_FULL, STRIPE_PROD_STUDENT
from yatl.helpers import H5, BEAUTIFY, CAT, XML
import stripe, decimal, datetime

stripe.api_key = STRIPE_SKEY

# stripe_tool (diagnostic tool)
@action('stripe_tool', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('accounting')
def stripe_tool():
	access = session['access']	#for layout.html
	form = Form([Field('object_type', comment="e.g. 'Customer', 'Subscription'"),
	      		Field('object_id')],
				keep_values=True, formstyle=form_style)
	header = H5('Stripe_Tool - inspect Stripe Objects')
	footer = ""
	object={}

	if form.accepted:
		try:
			object = eval(f"stripe.{form.vars.get('object_type')}.retrieve(\'{form.vars.get('object_id')}\')")
			footer = BEAUTIFY(object)
		except Exception as e:
			flash.set(str(e))
	return locals()

#get dues details for membership type
def stripe_get_dues(membership):
	product = stripe.Product.retrieve(eval(f"STRIPE_PROD_{membership.upper()}"))
	price = stripe.Price.retrieve(product.default_price)
	session['membership'] = membership
	session['dues'] = str(decimal.Decimal(price.unit_amount)/100)
	session['subscription'] = True if price.recurring else False
	
#update Stripe Customer Record with current primary email
def stripe_update_email(member):
	if member.Pay_cust:
		try:	#check customer still exists on Stripe
			cus = stripe.Customer.retrieve(member.Pay_cust)
			stripe.Customer.modify(member.Pay_cust, email=primary_email(member.id))
		except Exception as e:
			member.update_record(Pay_cust=None, Pay_subs=None, Pay_next=None)

#process a Stripe transaction
def stripe_process_charge(dict_csv, bank, reference, timestamp, amount, fee):
	acdues = db(db.CoA.Name == "Membership Dues").select().first()
	actkts = db(db.CoA.Name == "Ticket sales").select().first()
	charge = stripe.Charge.retrieve(dict_csv['Source'])
	member = db(db.Members.Pay_cust==charge.customer).select().first()
	notes = f"{member_name(member.id)} {primary_email(member.id)}"
	if dict_csv['Type']=='charge':
		if charge.description=='Subscription update' or (member.Charged and amount>=member.Charged):
			#dues paid, charge may also cover an event (auto renewal or manual)
			if (charge.description or '').startswith('Subscription'):
				customer = stripe.Customer.retrieve(charge.customer)
				notes += ' Subscription: '+ customer.subscriptions.data[0].id
				member.update_record(Pay_next=datetime.datetime.fromtimestamp(customer.subscriptions.data[0].current_period_end).date())
			product = stripe.Product.retrieve(eval(f"STRIPE_PAID_{member.Membership.upper()}"))
			duesprice = stripe.Price.retrieve(product.default_price)
			duesamount = decimal.Decimal(duesprice.unit_amount)/100
			duesfee = (duesamount * fee)/amount	#prorate fee
			nowpaid = newpaiddate(member.Paiddate, timestamp=timestamp)
			db.Dues.insert(Member=member.id, Amount=duesamount, Date=timestamp.date(),
				Notes='Stripe', Prevpaid=member.Paiddate, Nowpaid=nowpaid, Status=member.Membership)
			member.update_record(Paiddate=nowpaid, Charged=None)
			db.AccTrans.insert(Bank = bank.id, Account = acdues.id, Amount = duesamount,
					Fee = duesfee, Accrual = False, Timestamp = timestamp,
					Reference = reference, Notes = notes)
			fee -= duesfee
			amount -= duesamount

		if amount > 0:	#presumably apply to event reservations
			resvtn=db((db.Reservations.Member==member.id)&(db.Reservations.Charged>=amount)).select(
							orderby=db.Reservations.Modified).first()
			if resvtn:
				db.AccTrans.insert(Bank = bank.id, Account = actkts.id, Amount = amount, Fee = fee,
					Timestamp = timestamp, Event = resvtn.Event, Reference = reference, Accrual = False, Notes = notes)
				resvtn.update_record(Paid=(resvtn.Paid or 0) + amount, Charged = resvtn.Charged - amount, Checkout=None)
				amount = 0
	return amount	#if not zero will be stored as unallocated

#display Stripe Checkout form to enter new card credentials
@action('stripe_update_card', method=['GET'])
@action.uses("stripe_checkout.html", session)
@checkaccess(None)
def stripe_update_card():
	access = session['access']	#for layout.html
	stripe_session_id = request.query.get('stripe_session_id')
	stripe_pkey = STRIPE_PKEY
	return locals()

#new card successfully registered using checkout
@action('stripe_switched_card', method=['GET'])
@action.uses("stripe_checkout.html", session, db, flash)
@checkaccess(None)
def stripe_switched_card():
	access = session['access']	#for layout.html
	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]

	stripe_session = stripe.checkout.Session.retrieve(session['stripe_session_id'], expand=['setup_intent'])
	stripe.Customer.modify(member.Pay_cust,
				invoice_settings={'default_payment_method': stripe_session.setup_intent.payment_method})
	stripe.Subscription.modify(member.Pay_subs,
				default_payment_method=stripe_session.setup_intent.payment_method)
	flash.set('Thank you for updating your credit card information!')
	notify_support(member, 'Credit Card Update', 'Credit card updated.')
	redirect(URL('stripe_view_card'))

@action('stripe_view_card', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def stripe_view_card():
	access = session['access']	#for layout.html

	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]
	
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
	      XML(f"Your next renewal payment of ${duesamount} will be charged to {paymentmethod.card.brand.capitalize()} \
....{paymentmethod.card.last4} exp {paymentmethod.card.exp_month}/{paymentmethod.card.exp_year} on {renewaldate}.<br><br>"))
	
	form = Form([], submit_value='Update Card on File')

	if form.accepted:
		stripe_session = stripe.checkout.Session.create(
		  payment_method_types=['card'],
		  mode='setup',
		  customer=member.Pay_cust,
		  setup_intent_data={},
		  success_url=URL('stripe_switched_card', scheme=True),
		  cancel_url=URL('index', scheme=True)
		)
		session['stripe_session_id'] = stripe_session.stripe_id
		redirect(URL('stripe_update_card', vars=dict(stripe_session_id=stripe_session.id)))
	return locals()

def stripe_cancel_subscription(member):
	if member.Pay_subs:	#delete Stripe subscription if applicable
		try:
			stripe.Subscription.delete(member.Pay_subs)
		except Exception as e:
			pass
	return False

#daily maintence for subscriptions
def stripe_subscription_maintenance(member):	#return True if subscription no longer current
	product = stripe.Product.retrieve(eval(f"STRIPE_PROD_{member.Membership.upper()}"))
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

@action('stripe_checkout', method=['GET'])
@action.uses("stripe_checkout.html", db, session, flash)
@checkaccess(None)
def stripe_checkout():
	access = session['access']	#for layout.html
	if (not session.get('membership') and not session.get('event_id')) or not session.get('member_id'):
		redirect(URL('index'))	#protect against regurgitated old requests

	member = db.Members[session.get('member_id')]
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
		product = stripe.Product.retrieve(eval(f"STRIPE_PROD_{session.get('membership').upper()}"))
		price = stripe.Price.retrieve(product.default_price)
		params['dues'] = session.get('dues')
		params['membership'] = session.get('membership')
		if price.recurring:
			mode = 'subscription'
		items.append(dict(price = product.default_price, quantity = 1))
		
	if session.get('event_id'):			#event registration
		event = db.Events[session.get('event_id')]
		tickets_tbc = res_tbc(member.id, event.id)
		if tickets_tbc:
			params['event_id'] = event.id
			params['tickets_tbc'] = tickets_tbc
			items.append(dict(price_data = dict(currency='usd', unit_amount=int(tickets_tbc*100),
						product=STRIPE_EVENT), description = event.Description, quantity=1))
		 
	stripe_session = stripe.checkout.Session.create(
	  customer=member.Pay_cust,
	  payment_method_types=['card'], line_items=items, mode=mode,
	  success_url=URL('stripe_checkout_success', vars=params, scheme=True),
	  cancel_url=session.get('url_prev')
	)
	stripe_session_id = stripe_session.stripe_id		#for use in template
	session['stripe_session_id'] = stripe_session.stripe_id
	stripe_pkey = STRIPE_PKEY
	return locals()

@action('stripe_checkout_success', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess(None)
def stripe_checkout_success():
	member = db.Members[session.get('member_id')]
	dues = decimal.Decimal(request.query.get('dues') or 0)
	tickets_tbc = decimal.Decimal(request.query.get('tickets_tbc') or 0)
	stripe_session = stripe.checkout.Session.retrieve(session.get('stripe_session_id'))

	if not stripe_session or decimal.Decimal(stripe_session.amount_total)/100 != tickets_tbc + dues:
		raise Exception(f"Unexpected checkout_success callback received from Stripe, member {member.id}, event {session.get('event_id')}")
		redirect(URL('index'))

	subject = 'Registration Confirmation' if tickets_tbc>0 else 'Thank you for your membership payment'
	message = f"{msg_header(member, subject)}<br><b>Received: ${dues+tickets_tbc}</b><br>"
	
	if dues>0:
		next = None
		if stripe_session.subscription:
			subscription = stripe.Subscription.retrieve(stripe_session.subscription)
			next = datetime.datetime.fromtimestamp(subscription.current_period_end).date()
		member.update_record(Membership=request.query.get('membership'),
			Pay_subs=stripe_session.subscription, Pay_next=next, Charged=dues)
		message += 'Thank you, your membership is now current.</b><br>'
		
	if tickets_tbc>0:
		host_reservation = db((db.Reservations.Event==request.query.get('event_id'))&(db.Reservations.Member == member.id)\
					&(db.Reservations.Host == True)).select().first()
		message += '<br><b>Your registration is now confirmed:</b><br>'
		message +=event_confirm(request.query.get('event_id'), member.id, dues+tickets_tbc)
		host_reservation.update_record(Charged = (host_reservation.Charged or 0) + tickets_tbc, Checkout = None)

	msg_send(member,subject, message)
	
	flash.set('Thank you for your payment. Confirmation has been sent by email!')
	session['membership'] = None
	session['dues'] = None
	session['event_id'] = None
	session['stripe_session_id'] = None
	if dues:
		flash.set('Confirmation has been sent by email. Please review your mailing list subscriptions.')
		session['url'] = URL('index')
		redirect(URL(f"emails/Y/{member.id}/select"))
		#it would be nice to go right to edit the subscription of the primary email,
		#but a side effect of Stripe Checkout seems to be that the first 'submit' doesn't work
		#I think this is CSRF protection at work.
		#redirect(URL(f"emails/Y/{member.id}/edit/{db(db.Emails.Member == member.id).select(orderby=~db.Emails.Modified).first().id}"))
	redirect(URL('index'))
