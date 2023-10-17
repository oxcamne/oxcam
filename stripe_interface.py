"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are the implementation of the Stripe payment processor
interface
"""
from py4web import action, response, redirect, Field, request, URL
from py4web.utils.factories import Inject
from .common import db, session, flash
from .models import primary_email, member_name
from .controllers import checkaccess, form_style, grid_style
from .utilities import notify_support, newpaiddate
from py4web.utils.form import Form, FormStyleDefault
from py4web.utils.grid import Grid, GridClassStyle
from .settings import STRIPE_SKEY, STRIPE_PKEY, SOCIETY_DOMAIN, STRIPE_FULL, STRIPE_STUDENT
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
	price_id = eval(f"STRIPE_{membership.upper()}")
	price = stripe.Price.retrieve(price_id)
	session['membership'] = membership
	session['dues'] = str(decimal.Decimal(price.unit_amount)/100)
	session['subscription'] = True if price.recurring else False
	
#update Stripe Customer Record with current primary email
def stripe_update_email(member):
	if member.Stripe_id:
		pk = STRIPE_PKEY	#use the public key on the client side	
		try:	#check customer still exists on Stripe
			cus = stripe.Customer.retrieve(member.Stripe_id)
			stripe.Customer.modify(member.Stripe_id, email=primary_email(member.id))
		except Exception as e:
			member.update_record(Stripe_id=None, Stripe_subscription=None, Stripe_next=None)

#process a Stripe transaction
def stripe_process_charge(dict_csv, bank, reference, timestamp, amount, fee):
	acdues = db(db.CoA.Name == "Membership Dues").select().first()
	actkts = db(db.CoA.Name == "Ticket sales").select().first()
	charge = stripe.Charge.retrieve(dict_csv['Source'])
	member = db(db.Members.Stripe_id==charge.customer).select().first()
	notes = f"{member_name(member.id)} {primary_email(member.id)}"
	if dict_csv['Type']=='charge':
		if charge.description=='Subscription update' or (member.Charged and amount>=member.Charged):
			#dues paid, charge may also cover an event (auto renewal or manual)
			if (charge.description or '').startswith('Subscription'):
				customer = stripe.Customer.retrieve(charge.customer)
				notes += ' Subscription: '+ customer.subscriptions.data[0].id
				member.update_record(Stripe_next=datetime.datetime.fromtimestamp(customer.subscriptions.data[0].current_period_end).date())
			duesprice = stripe.Price.retrieve(eval(f'STRIPE_{member.Membership.upper()}'))
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
			
@action('stripe_update_card', method=['GET'])
@action.uses("stripe_checkout.html", session)
@checkaccess(None)
def stripe_update_card():
	access = session['access']	#for layout.html
	stripe_session_id = request.query.get('stripe_session_id')
	stripe_pkey = STRIPE_PKEY
	return locals()
	
@action('stripe_switched_card', method=['GET'])
@action.uses("stripe_checkout.html", session, db, flash)
@checkaccess(None)
def stripe_switched_card():
	access = session['access']	#for layout.html
	stripe.api_key = STRIPE_SKEY
	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]

	stripe_session = stripe.checkout.Session.retrieve(session['stripe_session_id'], expand=['setup_intent'])
	stripe.Customer.modify(member.Stripe_id,
				invoice_settings={'default_payment_method': stripe_session.setup_intent.payment_method})
	stripe.Subscription.modify(member.Stripe_subscription,
				default_payment_method=stripe_session.setup_intent.payment_method)
	flash.set('Thank you for updating your credit card information!')
	notify_support(member, 'Credit Card Update', 'Credit card updated.')
	redirect(URL('update_card'))

@action('update_card', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def update_card():
	access = session['access']	#for layout.html
	stripe.api_key = STRIPE_SKEY

	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]
	
	if member.Stripe_subscription and member.Stripe_subscription!='Cancelled':
		try:	#check subscription still exists on Stripe
			subscription = stripe.Subscription.retrieve(member.Stripe_subscription)
		except Exception as e:
			member.update_record(Stripe_subscription=None, Stripe_next=None)
	if not (member.Stripe_subscription and member.Stripe_subscription!='Cancelled'):
		redirect(URL('index'))	#Stripe subscription doesn't exist
		
	paymentmethod = stripe.PaymentMethod.retrieve(subscription.default_payment_method)
	renewaldate = member.Stripe_next.strftime('%b %d, %Y')
	duesamount = decimal.Decimal(subscription.plan.amount)/100
	header = CAT(H5('Membership Subscription'),
	      XML(f"Your next renewal payment of ${duesamount} will be charged to {paymentmethod.card.brand.capitalize()} \
....{paymentmethod.card.last4} exp {paymentmethod.card.exp_month}/{paymentmethod.card.exp_year} on {renewaldate}.<br><br>"))
	
	form = Form([], submit_value='Update Card on File')

	if form.accepted:
		stripe_session = stripe.checkout.Session.create(
		  payment_method_types=['card'],
		  mode='setup',
		  customer=member.Stripe_id,
		  setup_intent_data={},
		  success_url=URL('stripe_switched_card', scheme=True),
		  cancel_url=URL('index', scheme=True)
		)
		session['stripe_session_id'] = stripe_session.stripe_id
		redirect(URL('stripe_update_card', vars=dict(stripe_session_id=stripe_session.id)))
	return locals()
