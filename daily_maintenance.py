#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
this is used in PythonAnywhere environment, where it is run as a Pythonanywhere scheduled task:
	py4web/py4web.py call py4web/apps oxcam.daily_maintenance.daily_maintenance
it can be run in vscode using a configuration:
        {
            "name": "Python: daily",
            "type": "python",
            "request": "launch",
            "program": "C:/Users/David/SkyDrive/py4web/py4web.py",
            "args": ["call", "apps", "oxcam.daily_maintenance.daily_maintenance"],
            "console": "integratedTerminal",
            "justMyCode": false,
        }

"""
import datetime
import os
from .common import db, auth, logger
from .settings_private import SOCIETY_DOMAIN, STRIPE_SKEY, IS_PRODUCTION, SUPPORT_EMAIL,\
	LETTERHEAD, SOCIETY_NAME
from .utilities import notify_support, member_greeting
from .models import primary_email
from py4web import URL
from yatl.helpers import HTML, XML
import stripe
stripe.api_key = STRIPE_SKEY

def daily_maintenance():
	#keep only most recent month's backup plus monthly (month day 1) backups for one year
	items = os.listdir(".")
	dname = datetime.date.today().strftime("%d") + '.csv'
	yname = (datetime.date.today()-datetime.timedelta(days=365)).strftime("%Y%m01") + '.csv'
	for i in items:
		if (i.endswith(dname) and (datetime.date.today().day != 1)) or i.endswith(yname):
			os.remove(i)

	file=open(f'{SOCIETY_DOMAIN}_backup_{datetime.date.today().strftime("%Y%m%d")}.csv',
					'w', encoding='utf-8', newline='')
	db.export_to_csv_file(file)

	#send renewal reminders at 9 day intervals from one interval before to two intervals after renewal date
	#note that full memberships will generally be auto renewing Stripe subscriptions, but legacy memberships and
	#student memberships still need manual renewal.
	interval = 9
	first_date = datetime.date.today() - datetime.timedelta(days=interval*2)
	last_date = datetime.date.today() + datetime.timedelta(days=interval)

	members = db((db.Members.Paiddate>=first_date)&(db.Members.Paiddate<=last_date)&(db.Members.Membership!=None)&\
				(db.Members.Stripe_subscription==None)&(db.Members.Charged==None)).select()
	for m in members:
		to = primary_email(m.id) if IS_PRODUCTION else SUPPORT_EMAIL
		bcc = SUPPORT_EMAIL if IS_PRODUCTION else None

		if (m.Paiddate - datetime.date.today()).days % interval == 0:
			text = f"{LETTERHEAD.replace('&lt;subject&gt;', 'Renewal Reminder')}{member_greeting(m)}"
			text += f"<p>This is a friendly reminder that your {SOCIETY_NAME} membership expiration \
date is/was {m.Paiddate.strftime('%m/%d/%Y')}. Please renew by <a href={URL('index', scheme=True)}> logging in</a> \
and selecting join/renew from the menu of choices, \
or cancel membership to receive no futher reminders.</p><p>\
We are very grateful for your membership support and hope that you will renew!</p>\
If you have any questions, please contact {SUPPORT_EMAIL}"
			if IS_PRODUCTION:
				auth.sender.send(to=primary_email(m.id), sender=SUPPORT_EMAIL, subject='Renewal Reminder', body=HTML(XML(text)))
			logger.info(f"Renewal Reminder sent to {primary_email(m.id)}")

	subs = db((db.Members.Stripe_subscription!=None)&(db.Members.Stripe_subscription!='Cancelled')&(db.Members.Stripe_next<datetime.date.today())).select()
	for m in subs:
		to = primary_email(m.id) if IS_PRODUCTION else SUPPORT_EMAIL
		bcc = SUPPORT_EMAIL if IS_PRODUCTION else None

		try:	#check subscription still exists on Stripe
			subscription = stripe.Subscription.retrieve(m.Stripe_subscription)
			if not subscription.canceled_at:
				continue		#canceled_at set when last payment 	attempt fails
			#note after auto-pay fails and cancels the subsription, it can no longer be deleted from Stripe
			text = f"{LETTERHEAD.replace('&lt;subject&gt;', 'Membership Renewal Failure')}{member_greeting(m)}"
			text += f"<p>The renewal payment for your membership has failed as your \
card details on file no longer worked, and as a result your membership has been cancelled. </p><p>\
We hope you will <a href={URL('index', scheme=True)}> reinstate your membership</a>, \
but in any case we are grateful for your past support!</p>\
If you have any questions, please contact {SUPPORT_EMAIL}"
			auth.sender.send(to=to, bcc=bcc, sender=SUPPORT_EMAIL, subject='Membership Renewal Failure', body=HTML(XML(text)))
		except Exception as e:	#assume payment has failed
			pass
				
		logger.info(f"Membership Subscription Cancelled {primary_email(m.id)}")
		notify_support(m, 'Membership Cancelled', f"{primary_email(m.id)} Stripe auto-renew failed")
		m.update_record(Stripe_subscription = 'Cancelled', Stripe_next=None, Modified=datetime.datetime.now())
	db.commit()
