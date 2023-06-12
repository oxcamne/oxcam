#!/usr/bin/env python
# -*- coding: utf-8 -*-
#this is used in PythonAnywhere environment, where it is run as a Pythonanywhere task:
#	python#.# /home/oxcamne/web2py/web2py.py -S init -M -R applications/init/modules/db_backup.py
#which in turn is run by the PythonAnywhere scheduler.
import datetime
import os
from .common import db, session, T, cache, auth, logger, authenticated, unauthenticated, flash
from .settings_private import *
from .models import *
from .controllers import member_greeting
from py4web import URL
from yatl.helpers import *
import stripe
stripe.api_key = STRIPE_SKEY

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
and selecting join/renew from the menu of choices</p><br><p>\
We are very grateful for your membership support!</p><br>\
If you have any questions, please contact {SUPPORT_EMAIL}"
		auth.sender.send(to=to, bcc=bcc, sender=SUPPORT_EMAIL, subject='Renewal Reminder', body=HTML(XML(text)))

subs = db((db.Members.Stripe_subscription!=None)&(db.Members.Stripe_subscription!='Cancelled')).select()
for m in subs:
	to = primary_email(m.id) if IS_PRODUCTION else SUPPORT_EMAIL
	bcc = SUPPORT_EMAIL if IS_PRODUCTION else None

	if m.Stripe_next < datetime.date.today():	#check if auto-pay has failed.
		try:	#check subscription still exists on Stripe
			subscription = stripe.Subscription.retrieve(m.Stripe_subscription)
			if not subscription.canceled_at:
				continue		#canceled_at set when last payment 	attempt fails
			#note after auto-pay fails and cancels the subsription, it can no longer be deleted from Stripe
			text = f"{LETTERHEAD.replace('&lt;subject&gt;', 'Membership Renewal Failure')}{member_greeting(m)}"
			text += f"<p>The renewal payment for your membership has failed as your \
card details on file no longer worked, and as a result your membership has been cancelled. </p><br><p>\
We hope you will <a href={URL('index', scheme=True)}> reinstate your membership</a>, \
but in any case we are grateful for your past support!</p><br>\
If you have any questions, please contact {SUPPORT_EMAIL}"
			auth.sender.send(to=to, bcc=bcc, sender=SUPPORT_EMAIL, subject='Membership Renewal Failure', body=HTML(XML(text)))
			
		except Exception as e:	#assume payment has failed
			pass
			
		m.update_record(Stripe_subscription = 'Cancelled', Stripe_next=None, Modified=datetime.datetime.now())
