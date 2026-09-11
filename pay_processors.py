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
from pathlib import Path
from py4web import action, redirect, Field, request, URL, HTTP
from py4web.utils import form
from .common import db, session, flash
from .models import primary_email, event_unpaid
from .session import checkaccess
from .utilities import notify_support, newpaiddate, msg_header, msg_send, event_confirm, set_default_mailing_lists
from py4web.utils.form import Form
from .settings import TIME_ZONE, PaymentProcessor, PAYMENTPROCESSORS, PAGE_BANNER
from yatl.helpers import H5, BEAUTIFY, CAT, XML
from py4web.utils.factories import Inject
import stripe, decimal, datetime, random, time

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


def _pending_event_registrations_for_checkout(metadata):
	member_id = getattr(metadata, 'member_id', None)
	event_id = getattr(metadata, 'event_id', None)
	if not member_id or not event_id:
		return []

	return db(
		(db.Reservations.Member == member_id) &
		(db.Reservations.Event == event_id) &
		(db.Reservations.Pending == True)
	).select()


def _clear_pending_event_registrations(metadata):
	for reservation in _pending_event_registrations_for_checkout(metadata):
		reservation.update_record(Pending=False)

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
					params={"email": primary_email(member.id), "name": f'{member.Firstname} {member.Lastname}',
							"phone": member.Cellphone}
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
			if member.Membership and member.Charged is not None and amount >= member.Charged:	
				# Dues paid, may also cover an event ticket
				if description and description.startswith('Subscription'):
					try:
						# This is a subscription payment - find the subscription to update the member record
						# There should only be one active subscription for this customer
						customer = stripe_client.v1.customers.retrieve(customer_id, params={"expand": ["subscriptions"]})

						subs = customer.subscriptions.data
						active_subs = [s for s in subs if s.status == "active" or s.status == "trialing"]
						if not active_subs:
							# No active subscriptions found - this shouldn't happen for a subscription payment
							return (amount, f"No active subscription found for customer {customer_id}")

						subscription = active_subs[0] if active_subs else None
						period_end = get_subscription_period_end(subscription)
						member.update_record(Pay_subs=subscription.id,
											next_date = datetime.datetime.fromtimestamp(period_end).date())

						notes += f" Subscription: {subscription.id}"
					except Exception as e:
						# Could not retrieve or update subscription
						notes += f" Subscription lookup failed: {str(e)}"
			
				try:
					duesamount = member.Charged
					duesfee = (duesamount * fee) / amount
					fee -= duesfee
					amount -= duesamount
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
						member.update_record(Paiddate=newpaiddate(member.Paiddate, timestamp), Charged=None)
					except Exception as e:
						return (amount, f"Failed to record membership dues transaction: {str(e)}")

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

							if not member.Membership and not member.Paiddate:
								# If this is a non-member paying for an event, check if ticket includes free membership
								ticket = db.Event_Tickets[resvtn.Ticket_]
								if ticket.New_member:
									#record dummy dues payment to include this member in the new members list
									db.AccTrans.insert(
										Bank=bank.id,
										Account=acdues.id,
										Amount=0,
										Member=member.id,
										Paiddate=None,
										Membership=ticket.Short_name,
										Fee=0,
										Accrual=False,
										Timestamp=timestamp,
										Reference=reference,
										Notes=notes
									)
									notes = f"{datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).strftime('%x')} {resvtn.Notes}" if resvtn.Notes else ''
									member.update_record(
										Membership=ticket.Short_name, 
										Paiddate=newpaiddate(resvtn.Created.date()),
										Notes=notes
									)
									#ensure the default mailing list subscriptions are in place in the primary email
									set_default_mailing_lists(member)
						except Exception as e:
							return (amount, f"Failed to record event transaction: {str(e)}")
				except Exception as e:
					# Could not process event reservation
					return (amount, f"Failed to process event reservation: {str(e)}")
				
		if dict_csv['Type'] == 'refund':
			charges = db((db.AccTrans.Bank == bank.id) & db.AccTrans.Notes.contains(source_id) & (db.AccTrans.Amount != 0)).select(
						orderby=~db.AccTrans.id
			)	#charge may be split between dues and event, refund event first. ignore dummy dues payment for free membership
			already_refunded = 0	#the amount of earlier refunds to be accounted for
			for charge in charges:
				if charge.Amount < 0:
					already_refunded -= charge.Amount
					continue
				charge_left = charge.Amount - already_refunded
				if charge_left <= 0:
					already_refunded -= charge.Amount
					continue
				refund_amount = min(charge_left, -amount)
				try:
					db.AccTrans.insert(
						Bank=bank.id,
						Account=charge.Account,
						Member=charge.Member,
						Amount= -refund_amount,
						Fee=fee,
						Timestamp=timestamp,
						Event=charge.Event,
						Reference=reference,
						Accrual=False,
						Notes=f"{source_id} refund"
					)
				except Exception as e:
					return (amount, f"Failed to record refund transaction: {str(e)}")
				amount += refund_amount
				if amount == 0:
					break		# refund accounted for
		
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
				params={"email": primary_email(member.id), "name": f'{member.Firstname} {member.Lastname}',
						"phone": member.Cellphone}
			)
		else:
			customer = stripe_client.v1.customers.create(
				params={"email": primary_email(member.id), "name": f'{member.Firstname} {member.Lastname}',
						"phone": member.Cellphone}
			)
			member.update_record(Pay_cust=customer['id'], Pay_source='stripe')

		if session.get('membership'):
			# This includes a membership subscription
			product = stripe_client.v1.products.retrieve(
				stripeprocessor().dues_products[session['membership']]
			)
			price = stripe_client.v1.prices.retrieve(product['default_price'])
			params['dues'] = session.get('dues', 0)
			params['membership'] = session.get('membership')

			if price['recurring']:
				mode = 'subscription'
			if decimal.Decimal(session.get('dues') or 0) or mode == 'subscription':
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
			"expires_at": int(time.time()) + 30 * 60,
			"success_url": URL('stripe_checkout_success', vars=params, scheme=True),
			"cancel_url": back
		}
		checkout_params["metadata"] = {key: value for key, value in params.items()}

		if mode == 'payment':
			checkout_params["payment_intent_data"] = {
				"setup_future_usage": "off_session",
				"metadata": checkout_params["metadata"]
			}
		elif mode == 'subscription' and not decimal.Decimal(session.get('dues') or 0):
			# Defer the first charge to the end of the first billing cycle by giving the
			# subscription a full free trial. Stripe then bills on the next renewal date.
			recurring = price['recurring']
			interval = recurring['interval']
			interval_days = {
				'day': 1,
				'week': 7,
				'month': 30,
				'year': 365,
			}.get(interval, 0)
			if interval_days:
				checkout_params["subscription_data"] = {
					"trial_period_days": int(recurring['interval_count']) * interval_days
				}

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

@action('stripe_webhook', method=['POST'])
@action.uses(db)
def stripe_webhook():
	secret_path = Path(__file__).resolve().parents[2] / '.env.secret'
	with open(secret_path) as f:
		endpoint_secret = f.read().strip()
	if not endpoint_secret:
		raise HTTP(500, "Stripe webhook secret is not configured")

	payload = request.body.read()
	signature = request.headers.get('Stripe-Signature')
	try:
		event = stripe.Webhook.construct_event(payload, signature, endpoint_secret)
	except (ValueError, stripe.error.SignatureVerificationError):
		raise HTTP(400, "Invalid Stripe webhook")

	event_type = event['type']
	checkout_session = event['data']['object']
	metadata = getattr(checkout_session, 'metadata', None) or {}
	if metadata:
		member_id = getattr(metadata, 'member_id', None)
		member = db.Members[member_id] if member_id else None
		event_id = getattr(metadata, 'event_id', None)
		customer_id = getattr(checkout_session, 'customer', None)
		dues = decimal.Decimal(getattr(metadata, 'dues', 0))
		tickets_tbc = decimal.Decimal(getattr(metadata, 'tickets_tbc', 0))

	if event_type == 'checkout.session.expired':
		reservations = _pending_event_registrations_for_checkout(metadata)
		for reservation in reservations:
			reservation.update_record(Pending=False, Provisional=True)
		if len(reservations) > 0:
			subject = 'Event Registration Failed'
			message = f"{msg_header(member, subject)}<b>Please re-register if unconfirmed guests wish to attend this event.</b><br>"
			if tickets_tbc:
				message += event_confirm(event_id, member.id, dues)
			msg_send(member, subject, message)
		return dict(received=True)

	if event_type != 'checkout.session.completed':
		return dict(received=True)

	if checkout_session.mode not in ('payment', 'subscription'):
		return dict(received=True)
	if checkout_session.payment_status not in ('paid', 'no_payment_required'):
		return dict(received=True)

	checkout_id = checkout_session['id']
	payment_intent_id = getattr(checkout_session, 'payment_intent', None)
	if hasattr(payment_intent_id, 'id'):
		payment_intent_id = payment_intent_id.id
	dedup_query = db.Stripe_Checkout_Events.Checkout == checkout_id
	if db(dedup_query).count():
		return dict(received=True)

	if not member or customer_id != member.Pay_cust:
		raise HTTP(400, "Checkout customer does not match member")

	# Make the card selected during Checkout the default for future invoices.
	payment_method_id = None
	if payment_intent_id:
		payment_intent = stripe_client.v1.payment_intents.retrieve(payment_intent_id)
		payment_method_id = getattr(payment_intent, 'payment_method', None)

	subscription_id = getattr(checkout_session, 'subscription', None) if checkout_session else None
	if not payment_method_id and subscription_id:
		subscription = stripe_client.v1.subscriptions.retrieve(subscription_id)
		payment_method_id = getattr(subscription, 'default_payment_method', None)

	if hasattr(payment_method_id, 'id'):
		payment_method_id = payment_method_id.id
	if payment_method_id:
		stripe_client.v1.customers.update(
			member.Pay_cust,
			params={"invoice_settings": {"default_payment_method": payment_method_id}}
		)

	try:
		db.Stripe_Checkout_Events.insert(Checkout=checkout_id)
	except Exception:
		if db(dedup_query).count():
			return dict(received=True)
		raise

	_clear_pending_event_registrations(metadata)

	if dues or checkout_session.mode == 'subscription':
		member.update_record(Membership=getattr(metadata, 'membership', None), Charged=dues)
		if checkout_session.mode == 'subscription' and subscription_id:
			subscription = stripe_client.v1.subscriptions.retrieve(subscription_id)
			period_end = get_subscription_period_end(subscription)
			next_date = datetime.datetime.fromtimestamp(period_end).date() if period_end else None
			member.update_record(Pay_subs=subscription.id, Pay_next=next_date, Pay_modern=True)

	if tickets_tbc:
		host_reservation = db(
			(db.Reservations.Event == event_id) &
			(db.Reservations.Member == member.id) &
			(db.Reservations.Host == True)
		).select().first()
		if not host_reservation:
			raise HTTP(400, "Checkout reservation was not found")
		host_reservation.update_record(Charged=(host_reservation.Charged or 0) + tickets_tbc, Checkout=None)

	subject = 'Registration Confirmation' if tickets_tbc else 'Thank you for your membership payment'
	message = f"{msg_header(member, subject)}<b>Received: {locale.currency(dues + tickets_tbc)}</b><br>"
	if tickets_tbc:
		message += event_confirm(event_id, member.id, dues)
	msg_send(member, subject, message)
	return dict(received=True)

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

#upgrade legacy subscription to modern SCA-compliant subscription with new card details
def upgrade_subscription(member, payment_method_id):
	if not (payment_method_id and member.Pay_subs and member.Pay_subs != 'Cancelled' and not member.Pay_modern):
		return

	try:
		old_subscription = stripe_client.v1.subscriptions.retrieve(member.Pay_subs)

		legacy_period_end = get_subscription_period_end(old_subscription)
		modern_price_id = old_subscription.items.data[0].price.id
		idempotency_key = f"upgrade_subscription:{old_subscription.id}:{payment_method_id}"

		new_subscription = stripe_client.v1.subscriptions.create(
			params={
				"customer": member.Pay_cust,
				"default_payment_method": payment_method_id,
				"billing_cycle_anchor": legacy_period_end,
				"proration_behavior": "none",
				"collection_method": "charge_automatically",
				"items": [{"price": modern_price_id}],
			},
			options={"idempotency_key": idempotency_key}
		)

		member.update_record(Pay_subs=new_subscription.id, Pay_modern=True)

		try:
			stripe_client.v1.subscriptions.cancel(old_subscription.id)
		except Exception:
			# Ignore cancellation failures caused by duplicate POSTs or already-cancelled subscriptions.
			pass
	except Exception as e:
		notify_support(member.id, 'Subscription Upgrade Failed', f'Failed to upgrade subscription: {str(e)}')

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

	# Update customer and subscription with the new payment method
	stripe_client.v1.customers.update(
		member.Pay_cust,
		params={"invoice_settings": {"default_payment_method": payment_method_id}}
	)
	stripe_client.v1.subscriptions.update(
		member.Pay_subs,
		params={"default_payment_method": payment_method_id}
	)

	flash.set('Thank you for updating your credit card information!')
	notify_support(member.id, 'Credit Card Update', 'Credit card updated.')

	session['stripe_session_id'] = None
	session['checkout_mode'] = None
	redirect(URL('stripe_view_card'))

@action('stripe_check_upgrade', method=['GET', 'POST'])
@preferred
@checkaccess(None)
def stripe_check_upgrade():
	access = session.access  # for layout.html

	if not session.member_id:
		redirect(URL('my_account'))
	member = db.Members[session.member_id]

	header = CAT(H5("Update to our new billing system"),
		XML("We’ve updated how subscriptions are billed. <br>Because you just added a new payment method, \
we can move your subscription to the new more secure system now.<br>Your price and renewal date will stay the same.<br><br>"),
"By continuing, you agree to update your subscription to our new billing system using your saved payment method.")

	form = Form([], submit_value='Continue')

	if form.accepted:
		upgrade_subscription(member, request.query.get('payment_method_id'))
		if request.query.get('flash'):
			flash.set(request.query.get('flash'))
		redirect(request.query.get('url'))

	return locals()


@action('stripe_checkout_success', method=['GET'])
@preferred
@checkaccess(None)
def stripe_checkout_success():
	member = db.Members[session.member_id]
	dues = decimal.Decimal(request.query.get('dues', 0))

	if not request.query.token or request.query.token != session.token:
		raise Exception(
			f"Unexpected checkout_success callback received from Stripe, "
			f"member {member.id}, event {session.get('event_id')}"
		)
	# Retrieve the checkout session to get the payment_intent
	checkout_session = stripe_client.v1.checkout.sessions.retrieve(
		session.get('stripe_session_id'),
		params={"expand": ["payment_intent", "subscription"]}
	)
	payment_method_id = None
	pi = getattr(checkout_session, 'payment_intent', None)
	if pi and not getattr(pi, 'id', None):
		# If the payment_intent was not expanded, retrieve it explicitly
		pi = stripe_client.v1.payment_intents.retrieve(pi)

	if pi and getattr(pi, 'status', None) == 'succeeded' and getattr(pi, 'payment_method', '').startswith('pm_') and getattr(pi, 'customer', None) == member.Pay_cust:
		payment_method_id = pi.payment_method
	
	processed = bool(session.get('stripe_session_id') and db(
		 db.Stripe_Checkout_Events.Checkout == session['stripe_session_id']
	).count())
	flash_text = (
		'Thank you for your payment. Confirmation has been sent by email!'
		if processed
		else 'Your payment is being processed. Confirmation will be sent by email.'
	)

	session['membership'] = None
	session['dues'] = None
	session['event_id'] = None
	session['stripe_session_id'] = None
	session['checkout_mode'] = None

	url = URL('my_account')
	if processed and dues:
		flash_text = "Confirmation has been sent by email. Please review your mailing list subscriptions."
		url = URL(f"emails/Y/{member.id}", vars=dict(back=URL('my_account')))
	elif payment_method_id and member.Pay_subs and member.Pay_subs != 'Cancelled' and not member.Pay_modern:
		redirect(URL('stripe_check_upgrade', vars=dict(payment_method_id=payment_method_id, url=url, flash=flash_text)))
	flash.set(flash_text)
	redirect(url)
"""
install implementation in base class
NOTE this creates a local list containing the implementing subclass instances,
which should be accessed using paymentprocessor() or stripeprocessor()
"""
PAYMENTPROCESSORS = [StripeProcessor(
	p.name, p.public_key, p.secret_key, p.dues_products
) if p.name == 'stripe' else p for p in PAYMENTPROCESSORS]
