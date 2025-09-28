#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This runs in it's own thread as a subprocess, started by __init__.py

It also spawns the daily maintenance and backup subprocess at midnight local time,
as a separate subprocess.
"""
import subprocess
import time, os, random, pickle, datetime, re, smtplib, markdown, locale
from pathlib import Path
from .common import db, logger
from .settings import VISIT_WEBSITE_INSTRUCTIONS, TIME_ZONE, ALLOWED_EMAILS, SUPPORT_EMAIL, SMTP_BULK
from .utilities import generate_hash, email_sender, template_expand, get_context
from .models import primary_email
from .daily_maintenance import daily_maintenance

def send_notice(notice):
	query = notice.Query
	left = notice.Left
	base_url = get_context('base_url')
	attachment = pickle.loads(notice.Attachment) if notice.Attachment else None
	list_unsubscribe_uri = None
	mailing = re.search(r"Mailings\.contains\((\d+)\)", notice.Query)
	if mailing:		#using a mailing list
		notice.Body += VISIT_WEBSITE_INSTRUCTIONS.replace('base_url', base_url)
		mailing_list = db.Email_Lists[mailing.group(1)]
	rows = db(eval(query)).select(left=eval(notice.Left) if notice.Left else None, distinct=True)
	#because sending may take several minutes, for fairness send in random order
	dispatch = random.sample(range(len(rows)), len(rows))

	sent = 0
	for i in dispatch:
		row = rows[i]
		member = db.Members[row.get('Member') or row.get('Members.id') or row.get('id')]
		to = row.get(db.Emails.Email) or primary_email(member.id)
		if not to or (ALLOWED_EMAILS and not (to.lower() in ALLOWED_EMAILS)):
			continue

		body_expanded = template_expand(notice.Body, locals())
		if mailing:
			list_unsubscribe_uri = f"{base_url}/unsubscribe/{row.get(db.Emails.id)}/{mailing_list.id}/{generate_hash(to)}"
			body_expanded += f"<br><br><a href={list_unsubscribe_uri}?in_msg=Y>Unsubscribe</a> from '{mailing_list.Listname}' mailing list."

		retry_delay = 2
		exception = None
		while True:
			try:
				email_sender(host=SMTP_BULK, subject=notice.Subject, sender=notice.Sender, to=to, bcc=eval(notice.Bcc),
					body=markdown.markdown(body_expanded), attachment=attachment, attachment_filename=notice.Attachment_Filename,
					list_unsubscribe=f"<{list_unsubscribe_uri}>" if mailing else None,
					list_unsubscribe_post="List-Unsubscribe=One-Click" if mailing else None,
				)
				sent += 1
				break
			except Exception as e:
				exception = e
				if retry_delay == 256:
					break	#give up after 510 seconds trying.
				time.sleep(retry_delay)
				retry_delay *= 2	#double delay each attempt
		
		if exception:
			email_sender(subject="Email Notice Send Failure", sender=notice.Sender, to=notice.Sender, bcc=SUPPORT_EMAIL,
				body=f'"{notice.Subject}" sent to {sent} of {len(rows)} failure: {exception}'
			)
			return

def email_daemon():
	path = Path(__file__).resolve().parent.parent.parent
	os.chdir(path)		 #working directory py4web
	old_now = None
	daily_maintenance_thread = None
	locale.setlocale(locale.LC_ALL, get_context('locale'))  #PythonAnywhere sets locale to 'C' in tasks
	#record start time:
	start_time = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	email_list = db(db.Email_Lists.id>0).select().first()
	if email_list:
		email_list.update_record(Daemon = start_time)
	db.commit()
	print(f"{str(path)} email_daemon {start_time.strftime("%x"+' %H:%M')} running")

	while True:
		db.get_connection_from_pool_or_new()
		email_list = db(db.Email_Lists.id>0).select().first()
		if email_list and email_list.Daemon > start_time:
			break	#exit this thread if reloaded
		now = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)

		# spawn daily maintenance at midnight
		if old_now and now.date()!=old_now.date():
			subprocess.Popen(['python', 'py4web.py', 'call', 'apps', 'oxcam.daily_maintenance.daily_maintenance'])
	
		notice = db(db.Email_Queue.id > 0).select().first()
		#logger.info(f"queue {db(db.Email_Queue.id > 0).count()}")
		if notice:
			db(db.Email_Queue.id==notice.id).delete()
			db.commit()
			send_notice(notice)
			continue    #until queue empty
		old_now = now
		time.sleep(5)
	print(f"{str(path)} email_daemon {start_time.strftime("%x"+' %H:%M')} exiting")
