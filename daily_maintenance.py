#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
this is spawned in it's own thread by the email daemon when local time passes midnight

It can also be run in development using a launch.json configuration:

        {
            "name": "Python: daily",
            "type": "python",
            "request": "launch",
            "program": "py4web.py",
            "args": [
                "call", "apps", "oxcam.daily_maintenance.daily_maintenance"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        },
 
"""
import datetime
import os
from pathlib import Path
from .common import db
from .settings import SOCIETY_SHORT_NAME, IS_PRODUCTION, SUPPORT_EMAIL,\
		SOCIETY_NAME, DB_URL, DATE_FORMAT, TIME_ZONE
from .utilities import member_greeting, email_sender
from .pay_processors import paymentprocessor
from .models import primary_email

def daily_maintenance():
	os.chdir(Path(__file__).resolve().parent.parent.parent) #working directory py4web
	#keep only most recent month's backup plus monthly (month day 1) backups for one year
	items = os.listdir(".")
	dname = datetime.date.today().strftime("%d") + '.csv'
	yname = (datetime.date.today()-datetime.timedelta(days=365)).strftime("%Y%m01") + '.csv'
	for i in items:
		if (i.endswith(dname) and (datetime.date.today().day != 1)) or i.endswith(yname):
			os.remove(i)

	trusted_date = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) - datetime.timedelta(days = 90)
	db((db.users.trusted == True) & (db.users.when_issued < trusted_date)).delete()
		#record trusted IP's for 90 days, no reCaptcha challenge
	untrusted_date = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) - datetime.timedelta(days = 7)
	db(((db.users.trusted==None) | (db.users.trusted!=True)) & (db.users.when_issued < untrusted_date)).delete()
		#keep unvalidated users only a week

	#send renewal reminders at 9 day intervals from one interval before to two intervals after renewal date
	#note that full memberships will generally be auto renewing Stripe subscriptions, but legacy memberships and
	#student memberships still need manual renewal.
	interval = 9
	first_date = datetime.date.today() - datetime.timedelta(days=interval*2)
	last_date = datetime.date.today() + datetime.timedelta(days=interval)

	members = db((db.Members.Paiddate>=first_date)&(db.Members.Paiddate<=last_date)&(db.Members.Membership!=None)&\
				(db.Members.Pay_subs==None)&(db.Members.Charged==None)).select()
	for m in members:
		if (m.Paiddate - datetime.date.today()).days % interval == 0:
			text = f"{member_greeting(m)}"
			text += f"<p>This is a friendly reminder that your {SOCIETY_NAME} membership expiration \
date is/was {m.Paiddate.strftime(DATE_FORMAT)}. Please renew by <a href={DB_URL}> logging in</a> \
and selecting join/renew from the menu of choices, \
or cancel membership to receive no futher reminders.</p><p>\
We are very grateful for your membership support and hope that you will renew!</p>\
If you have any questions, please contact {SUPPORT_EMAIL}"
			if IS_PRODUCTION:
				email_sender(to=primary_email(m.id), sender=SUPPORT_EMAIL, subject='Renewal Reminder', body=text)
			print(f"Renewal Reminder sent to {primary_email(m.id)}")

	subs = db((db.Members.Pay_subs!=None)&(db.Members.Pay_subs!='Cancelled')).select()
	for m in subs:
		if paymentprocessor(m.Pay_source).subscription_cancelled(m):	#subscription no longer operational
			if IS_PRODUCTION:
				text = f"{member_greeting(m)}"
				text += f"<p>We have been unable to process your auto-renewal and as a result your membership has been cancelled. </p><p>\
We hope you will <a href={DB_URL}> reinstate your membership</a>, \
but in any case we are grateful for your past support!</p>\
If you have any questions, please contact {SUPPORT_EMAIL}"
				db.commit()
				email_sender(to=primary_email(m.id), sender=SUPPORT_EMAIL,
					 bcc=SUPPORT_EMAIL, subject='Membership Renewal Failure', body=text)
			print(f"Membership Subscription Cancelled {primary_email(m.id)}")
			m.update_record(Pay_subs = 'Cancelled', Pay_next=None, Modified=datetime.datetime.now())
				
	db.commit()

	file=open(f'{SOCIETY_SHORT_NAME}_backup_{datetime.date.today().strftime("%Y%m%d")}.csv',
					'w', encoding='utf-8', newline='')
	db.export_to_csv_file(file)
