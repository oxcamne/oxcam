"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are the implementation of the Stripe payment processor
interface using MODERN Stripe APIs:

- PaymentIntents for one-time payments (SCA-compliant)
- SetupIntents for saving payment methods
- Subscriptions with automatic payment method attachment
- No legacy Charges API or Sources - fully migrated to PaymentMethods
"""
import locale
from py4web import action, redirect, Field, request, URL
from .common import db, session, flash
from .models import primary_email, event_unpaid
from .session import checkaccess
from .utilities import notify_support, newpaiddate, msg_header, msg_send, event_confirm
from py4web.utils.form import Form
from .settings import PaymentProcessor, PAYMENTPROCESSORS, PAGE_BANNER
from yatl.helpers import H5, BEAUTIFY, CAT, XML
from py4web.utils.factories import Inject
import stripe, decimal, datetime, random

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER))

# locate named or default processor
def paymentprocessor(name=session.pay_source):
	if not PAYMENTPROCESSORS:
		return None
	return next((p for p in PAYMENTPROCESSORS if p.name == name)) if name else PAYMENTPROCESSORS[0]

def stripeprocessor():
	if not PAYMENTPROCESSORS:
		return None
	return next((p for p in PAYMENTPROCESSORS if p.name == 'stripe'))

stripe_client = stripe.StripeClient(
	stripeprocessor().secret_key,
	stripe_version="2026-03-25.dahlia"
) if stripeprocessor() else None


def get_subscription_period_end(subscription):
	"""
	Return the effective current_period_end for a subscription, handling both:
	- legacy/simple subscriptions (subscription.current_period_end)
	- modern flexible billing (subscription.items.data[0].current_period_end)
	"""
	# Modern flexible billing: period lives on the subscription item
	try:
		items = getattr(subscription, "items", None)
		if items and getattr(items, "data", None):
			item = items.data[0]
			cpe = getattr(item, "current_period_end", None)
			if cpe:
				return cpe
	except Exception:
		pass

	# Legacy/simple: period lives on the subscription itself
	return getattr(subscription, "current_period_end", None)

class StripeProcessor(PaymentProcessor):
	"""
	Stripe payment processor with MODERN APIs (SCA-compliant, no legacy code):
	- PaymentIntents for one-time payments with setup_future_usage="off_session"
	- Checkout Sessions with payment_intent_data/subscription_data for SCA compliance
	- Automatic PaymentMethod saving and default_payment_method assignment
	- Compatible with Stripe API 2026-03-25 (Dahlia) and later
	"""

	# get dues details for membership type
	def get_dues(self, membership):
		product = stripe_client.v1.products.retrieve(stripeprocessor().dues_products.get(membership))
		price = stripe_client.v1.prices.retrieve(product['default_price'])
		return decimal.Decimal(price['unit_amount']) / 100

	# update Stripe Customer Record with current primary email
	def update_email(self, member):
		if member.Pay_cust:
			try:  # Check customer still exists on Stripe
				stripe_client.v1.customers.update(
					member.Pay_cust,
					params={"email": primary_email(member.id)}
				)
			except Exception:
				member.update_record(Pay_cust=None, Pay_subs=None, Pay_next=None)

	# process modern Stripe transactions using Payment Intents API (SCA-compliant)
	def process_charge(self, dict_csv, bank, reference, timestamp, amount, fee):
		acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first()
		actkts = db(db.CoA.Name.ilike("Ticket sales")).select().first()

		source_id = dict_csv['Source']

		# All modern transactions use Payment Intents - charges are just the captured result
		try:
			if source_id.startswith('pi_'):
				# Direct Payment Intent reference
				payment_obj = stripe_client.v1.payment_intents.retrieve(source_id)
			elif source_id.startswith('ch_'):
				# Charge from Payment Intent capture - get the associated payment intent
				charge = stripe_client.v1.charges.retrieve(source_id)
				payment_intent_id = charge.payment_intent

				if not payment_intent_id:
					return (amount, f"Charge {source_id} missing payment_intent (unexpected for checkout transaction)")

				payment_obj = stripe_client.v1.payment_intents.retrieve(payment_intent_id)
			else:
				# Unknown ID type
				return (amount, f"Unknown source type: {source_id}")
		except Exception as e:
			# Stripe API error
			return (amount, f"Stripe API error for {source_id}: {str(e)}")

		customer_id = payment_obj.customer
		if not customer_id:
			# Payment intent not associated with a customer - cannot process
			return (amount, f"Payment intent {source_id} not associated with a customer")

		description = payment_obj.description or ''  # Handle None descriptions

		try:
			member = db(db.Members.Pay_cust == customer_id).select().first()
		except Exception as e:
			return (amount, f"Database error retrieving member for customer {customer_id}: {str(e)}")

		if not member:
			# Customer not found in our database
			return (amount, f"Customer {customer_id} not found in database")

		notes = f"{source_id}"

		if dict_csv['Type'] == 'charge':
			# Check if this is a membership dues payment
			is_membership_payment = False

			if description and description.startswith('Subscription'):
				# This is a subscription-related payment
				is_membership_payment = True
			elif member.Membership and (member.Charged or 0) > 0 and amount >= member.Charged:
				# This appears to be a membership dues payment based on amount (non-subscription membership, e.g. Student)
				is_membership_payment = True

			if is_membership_payment and member.Membership:

				# Dues paid, may also cover an event ticket
				if description and description.startswith('Subscription'):
					try:
						# This is a subscription payment - find the subscription to update the member record
						# There should only be one active subscription for this customer
						customer = stripe_client.v1.customers.retrieve(customer_id, params={"expand": ["subscriptions"]})

						subs = customer.subscriptions.data
						active_subs = [s for s in subs if s.status == "active"]
						if not active_subs:
							# No active subscriptions found - this shouldn't happen for a subscription payment
							return (amount, f"No active subscription found for customer {customer_id}")

						subscription = active_subs[0] if active_subs else None
						member.update_record(Pay_subs=subscription.id)
						notes += f" Subscription: {subscription.id}"

						period_end = get_subscription_period_end(subscription)
						if period_end:
							next_date = datetime.datetime.fromtimestamp(period_end).date()
							member.update_record(Pay_next=next_date)
					except Exception as e:
						# Could not retrieve or update subscription
						notes += f" Subscription lookup failed: {str(e)}"
			
				try:
					if member.Membership not in self.dues_products:
						return (amount, f"Unknown membership type: {member.Membership}")

					product = stripe_client.v1.products.retrieve(self.dues_products[member.Membership])
					duesprice = stripe_client.v1.prices.retrieve(product['default_price'])
					duesamount = decimal.Decimal(duesprice['unit_amount']) / 100
					duesfee = (duesamount * fee) / amount
					nowpaid = newpaiddate(member.Paiddate, timestamp)
					try:
						db.AccTrans.insert(
							Bank=bank.id,
							Account=acdues.id,
							Amount=duesamount,
							Member=member.id,
							Paiddate=member.Paiddate,
							Membership=member.Membership,
							Fee=duesfee,
							Accrual=False,
							Timestamp=timestamp,
							Reference=reference,
							Notes=notes
						)
						member.update_record(Paiddate=nowpaid, Charged=None)
					except Exception as e:
						return (amount, f"Failed to record membership dues transaction: {str(e)}")

					fee -= duesfee
					amount -= duesamount
				except Exception as e:
					# Could not process membership dues
					return (amount, f"Failed to process membership dues: {str(e)}")

			if amount > 0:
				try:
					# Presumably apply to event reservations
					resvtn = db(
						(db.Reservations.Member == member.id) &
						(db.Reservations.Charged >= amount)
					).select(orderby=db.Reservations.Modified).first()

					if resvtn:
						try:
							db.AccTrans.insert(
								Bank=bank.id,
								Account=actkts.id,
								Member=member.id,
								Amount=amount,
								Fee=fee,
								Timestamp=timestamp,
								Event=resvtn.Event,
								Reference=reference,
								Accrual=False,
								Notes=notes
							)
							resvtn.update_record(Charged=resvtn.Charged - amount, Checkout=None)
							amount = 0
						except Exception as e:
							return (amount, f"Failed to record event transaction: {str(e)}")
				except Exception as e:
					# Could not process event reservation
					return (amount, f"Failed to process event reservation: {str(e)}")

		return (amount, notes)

	def cancel_subscription(self, member):
		if member.Pay_subs:
			try:
				stripe_client.v1.subscriptions.cancel(member.Pay_subs)
			except Exception:
				pass

	# daily maintenance for subscriptions (SCA-compliant with modern API field access)
	def subscription_cancelled(self, member):
		# Return True if subscription no longer current
		product = stripe_client.v1.products.retrieve(self.dues_products[member.Membership])

		if member.Pay_subs:
			try:
				subscription = stripe_client.v1.subscriptions.retrieve(member.Pay_subs)

				# Modern API: access price via items.data[0].price.id instead of subscription['plan']['id']
				current_price = subscription.items.data[0].price.id
				if current_price != product['default_price']:
					# Dues payment to change with next renewal but not retroactively
					stripe_client.v1.subscription_items.update(
						subscription.items.data[0].id,
						params={
							"price": product['default_price'],
							"proration_behavior": "none"
						}
					)

				if not subscription.canceled_at:
					return False  # Canceled_at set when last payment attempt fails

			except Exception:
				pass

		return True  # Can't retrieve subscription

	def checkout(self, back):
		if not (session.member_id and (session.get('membership') or session.get('event_id'))):
			redirect(URL('my_account'))

		member = db.Members[session.member_id]

		if member.Pay_cust:
			# Check customer still exists on Stripe
			try:
				customer = stripe_client.v1.customers.retrieve(member.Pay_cust)
			except Exception:
				member.update_record(Pay_cust=None, Pay_subs=None, Pay_source=None)

		mode = 'payment'
		items = []
		params = dict(member_id=member.id)  # params for checkout_success
		event = None

		if member.Pay_cust:
			stripe_client.v1.customers.update(
				member.Pay_cust,
				params={"email": primary_email(member.id)}
			)
		else:
			customer = stripe_client.v1.customers.create(
				params={"email": primary_email(member.id)}
			)
			member.update_record(Pay_cust=customer['id'], Pay_source='stripe')

		if session.get('membership'):
			# This includes a membership subscription
			product = stripe_client.v1.products.retrieve(
				stripeprocessor().dues_products[session['membership']]
			)
			price = stripe_client.v1.prices.retrieve(product['default_price'])
			params['dues'] = session.get('dues')
			params['membership'] = session.get('membership')

			if price['recurring']:
				mode = 'subscription'
			items.append(dict(price=product['default_price'], quantity=1))

		if session.get('event_id'):
			# Event registration
			event = db.Events[session.get('event_id')]
			tickets_tbc = event_unpaid(event.id, member.id)
			if tickets_tbc:
				params['event_id'] = event.id
				params['tickets_tbc'] = tickets_tbc
				items.append({
					'price_data': {
						'currency': 'usd',
						'unit_amount': int(tickets_tbc * 100),
						'product_data': {
							'name': 'Event Registration',
							'description': event.Description,
						}
					},
					'quantity': 1,
				})

		token = str(random.randint(10000, 999999))
		params['token'] = token
		session['token'] = token

		# SCA-compliant checkout using Stripe Checkout (handles Payment Intent creation internally)
		checkout_params = {
			"customer": member.Pay_cust,
			"payment_method_types": ['card'],
			"line_items": items,
			"mode": mode,
			"success_url": URL('stripe_checkout_success', vars=params, scheme=True),
			"cancel_url": back
		}

		if mode == 'payment':
			checkout_params["payment_intent_data"] = {
				"setup_future_usage": "off_session"
			}
		elif mode == 'subscription':
			pass

		stripe_session = stripe_client.v1.checkout.sessions.create(params=checkout_params)

		session['stripe_session_id'] = stripe_session['id']
		session['checkout_mode'] = mode

		redirect(stripe_session['url'])

	# display Stripe Checkout form to enter new card credentials (SCA-compliant)
	def update_card(self, member):
		token = str(random.randint(10000, 999999))
		session['token'] = token

		stripe_session = stripe_client.v1.checkout.sessions.create(
			params={
				"customer": member.Pay_cust,
				"payment_method_types": ["card"],
				"mode": "setup",
				"success_url": URL('stripe_switched_card', vars=dict(token=token), scheme=True),
				"cancel_url": URL('my_account', scheme=True)
			}
		)
		session['stripe_session_id'] = stripe_session['id']
		redirect(stripe_session['url'])

	def view_card(self):
		return URL('stripe_view_card')

@action('stripe_view_card', method=['GET', 'POST'])
@preferred
@checkaccess(None)
def stripe_view_card():
	access = session.access  # for layout.html

	if not session.member_id:
		redirect(URL('my_account'))
	member = db.Members[session.member_id]

	if member.Pay_subs and member.Pay_subs != 'Cancelled':
		try:  # check subscription still exists on Stripe
			subscription = stripe_client.v1.subscriptions.retrieve(member.Pay_subs)
		except Exception:
			member.update_record(Pay_subs=None, Pay_next=None)
	if not (member.Pay_subs and member.Pay_subs != 'Cancelled'):
		redirect(URL('my_account'))  # Stripe subscription doesn't exist

	paymentmethod = stripe_client.v1.payment_methods.retrieve(subscription.default_payment_method)
	renewaldate = member.Pay_next.strftime('%b %d, %Y')
	duesamount = decimal.Decimal(subscription.items.data[0].price.unit_amount) / 100
	header = CAT(
		H5('Membership Subscription'),
		XML(
			f"Your next renewal payment of {locale.currency(duesamount)} will be charged to "
			f"{paymentmethod.card.brand.capitalize()} ....{paymentmethod.card.last4} "
			f"exp {paymentmethod.card.exp_month}/{paymentmethod.card.exp_year} on {renewaldate}.<br><br>"
		)
	)

	form = Form([], submit_value='Update Card on File')

	if form.accepted:
		stripeprocessor().update_card(member)  # redirects to Stripe

	footer = CAT(
		XML("You will need to confirm your identity using a code sent to your email<br>"),
		"Then click 'Pay without Link' to enter your new card details. ")
	return locals()


# new card successfully registered using checkout (SCA-compliant with Payment Methods)
@action('stripe_switched_card', method=['GET'])
@preferred
@checkaccess(None)
def stripe_switched_card():
	member = db.Members[session.member_id]

	if not request.query.token or request.query.token != session.token:
		raise Exception(
			f"Unexpected checkout_success callback received from Stripe, "
			f"member {member.id}, event {session.get('event_id')}"
		)

	# Retrieve the checkout session to get the setup intent
	checkout_session = stripe_client.v1.checkout.sessions.retrieve(session['stripe_session_id'])
	setup_intent = stripe_client.v1.setup_intents.retrieve(checkout_session.setup_intent)
	payment_method_id = setup_intent.payment_method

	if not payment_method_id:
		flash.set('Error: No payment method was set up.')
		redirect(URL('my_account'))

	payment_method = stripe_client.v1.payment_methods.retrieve(payment_method_id)

	# Update customer and subscription with the new payment method
	stripe_client.v1.customers.update(
		member.Pay_cust,
		params={"invoice_settings": {"default_payment_method": payment_method['id']}}
	)
	stripe_client.v1.subscriptions.update(
		member.Pay_subs,
		params={"default_payment_method": payment_method['id']}
	)

	flash.set('Thank you for updating your credit card information!')
	notify_support(member.id, 'Credit Card Update', 'Credit card updated.')

	session['stripe_session_id'] = None

	redirect(URL('stripe_view_card'))

@action('stripe_checkout_success', method=['GET'])
@preferred
@checkaccess(None)
def stripe_checkout_success():
	member = db.Members[session.member_id]
	dues = decimal.Decimal(request.query.get('dues', 0))
	tickets_tbc = decimal.Decimal(request.query.get('tickets_tbc', 0))

	if not request.query.token or request.query.token != session.token:
		raise Exception(
			f"Unexpected checkout_success callback received from Stripe, "
			f"member {member.id}, event {session.get('event_id')}"
		)

	checkout_mode = session.get('checkout_mode', 'payment')

	subject = (
		'Registration Confirmation'
		if tickets_tbc > 0
		else 'Thank you for your membership payment'
	)
	message = (
		f"{msg_header(member, subject)}"
		f"<b>Received: {locale.currency(dues + tickets_tbc)}</b><br>"
	)

	if dues > 0:
		checkout_session = stripe_client.v1.checkout.sessions.retrieve(
			session.get('stripe_session_id'),
			params={"expand": ["subscription"]}
		)

		if getattr(checkout_session, "payment_method", None):
			stripe_client.v1.customers.update(
				member.Pay_cust,
				params={
					"invoice_settings": {
						"default_payment_method": checkout_session.payment_method
					}
				}
			)

		if checkout_mode == 'subscription':

			subscription = checkout_session.subscription
			next_date = None

			if subscription:
				period_end = get_subscription_period_end(subscription)
				if period_end:
					next_date = datetime.datetime.fromtimestamp(period_end).date()

				member.update_record(
					Pay_subs=subscription.id,
					Pay_next=next_date,
				)

		member.update_record(
			Membership=request.query.get('membership'),
			Charged=dues
		)

		message += 'Thank you, your membership is now current.</b><br>'

	if tickets_tbc > 0:
		host_reservation = db(
			(db.Reservations.Event == request.query.get('event_id')) &
			(db.Reservations.Member == member.id) &
			(db.Reservations.Host == True)
		).select().first()

		message += '<br><b>Your registration is now confirmed:</b><br>'

		host_reservation.update_record(
			Charged=(host_reservation.Charged or 0) + tickets_tbc,
			Checkout=None
		)

		message += event_confirm(
			request.query.get('event_id'),
			member.id,
			dues
		)

	msg_send(member, subject, message)

	flash.set('Thank you for your payment. Confirmation has been sent by email!')

	session['membership'] = None
	session['dues'] = None
	session['event_id'] = None
	session['stripe_session_id'] = None
	session['checkout_mode'] = None

	if dues:
		flash.set(
			'Confirmation has been sent by email. '
			'Please review your mailing list subscriptions.'
		)
		redirect(URL(f"emails/Y/{member.id}", vars=dict(back=URL('my_account'))))

	redirect(URL('my_account'))


"""
install implementation in base class
NOTE this creates a local list containing the implementing subclass instances,
which should be accessed using paymentprocessor() or stripeprocessor()
"""
PAYMENTPROCESSORS = [StripeProcessor(
	p.name, p.public_key, p.secret_key, p.dues_products
) if p.name == 'stripe' else p for p in PAYMENTPROCESSORS]
