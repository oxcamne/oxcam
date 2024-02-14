#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FOR Pythonanywhere THIS RUNS AS AN ALWAYS ON TASK
In development, it can be run using this configuration in launch.json:

        {
            "name": "Python: email",
            "type": "python",
            "request": "launch",
            "program": "py4web.py",
            "args": [
                "call", "apps", "oxcam.email_daemon.email_daemon"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        }
  
IDEALLY:
This runs in it's own thread as a daemon, started by __init__.py

It also spawns the daily maintenance and backup thread at midnight local time,
in a separate thread

NOTE PythonAnywhere doesn't support threading so this runs instead
	as a scheduled daily task, which requires a paid account
"""
import time, markmin, os, random, pickle, datetime, re
from pathlib import Path
from .common import db,logger,auth
from .settings import VISIT_WEBSITE_INSTRUCTIONS, TIME_ZONE, THREAD_SUPPORT, IS_PRODUCTION,\
	ALLOWED_EMAILS, SUPPORT_EMAIL
from .utilities import member_profile, event_confirm, member_greeting, emailparse, generate_hash
from .models import primary_email
from .daily_maintenance import daily_maintenance
from py4web import URL
from yatl.helpers import HTML, XML

def email_daemon():

	path = Path(__file__).resolve().parent.parent.parent
	os.chdir(path)		 #working directory py4web
	print(str(path)+' email_daemon running')
	old_now = None
	daily_maintenance_thread = None

	while True:
		now = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)

		if THREAD_SUPPORT:
			if old_now and now.date()!=old_now.date():
				from threading import Thread
				daily_maintenance_thread = Thread(target=daily_maintenance, daemon=True)
				daily_maintenance_thread.start()
	
		notice = db(db.Email_Queue.id > 0).select().first()
		if notice:
			bodyparts = emailparse(notice.Body, notice.Subject, notice.Query)
			attachment = pickle.loads(notice.Attachment) if notice.Attachment else None
			select_fields = [db.Members.id]
			list_unsubscribe_uri = None
			if 'Reservations.Event' in notice.Query:	#refers to Reservation
				select_fields.append(db.Reservations.Event)
			mailing = re.search(r"Mailings\.contains\((\d+)\)", notice.Query)
			if mailing:		#using a mailing list
				select_fields.append(db.Emails.Email)
				select_fields.append(db.Emails.id)
				bodyparts.append((VISIT_WEBSITE_INSTRUCTIONS, None))
				bodyparts.append((None, 'unsubscribe'))
				mailing_list = db.Email_Lists[mailing.group(1)]
			rows = db(eval(notice.Query)).select(*select_fields, left=eval(notice.Left) if notice.Left else None, distinct=True)
			#because sending may take several minutes, for fairness send in random order
			dispatch = random.sample(range(len(rows)), len(rows))
			for i in dispatch:
				row = rows[i]
				body = ''
				member = db.Members[row.get(db.Members.id)]
				to = row.get(db.Emails.Email) or primary_email(member.id)
				if not to or (not IS_PRODUCTION and not (to.lower() in ALLOWED_EMAILS)):
					continue
				for part in bodyparts:
					if part[0]:
						body += part[0]
					elif part[1] == 'greeting':
						body += member_greeting(member)
					elif part[1] == 'email':
						body += to
					elif part[1] == 'member':
						body += member_profile(member)
					elif part[1] == 'reservation':
						body += event_confirm(row.get(db.Reservations.Event), member.id)
					elif part[1] == 'unsubscribe':
						list_unsubscribe_uri = f"{notice.Scheme}unsubscribe/{row.get(db.Emails.id)}/{mailing_list.id}/{generate_hash(to)}"
						body += f"<br><br><a href={list_unsubscribe_uri}>Unsubscribe</a> from '{mailing_list.Listname}' mailing list."
				retry_seconds = 2
				while True:
					try:
						auth.sender.send(to=to, subject=notice.Subject, sender=notice.Sender, reply_to=notice.Sender,
					   		#TBD when py4web/mailer.py fixed
					   		#list_unsubscribe=f"<{list_unsubscribe_uri}>,<mailto:{SUPPORT_EMAIL}?subject=unsubscribe_{mailing_list.Listname.replace(' ','_')}>" if mailing else None,
							#list_unsubscribe_post="List-Unsubscribe=One-Click" if mailing else None,
		       				bcc=eval(notice.Bcc), body=HTML(XML(body)), attachments=attachment)
						break
					except Exception as e:
						if retry_seconds==14:
							logger.info("email send failure - retrying")
						time.sleep(retry_seconds)
						retry_seconds += 2
						if retry_seconds==20:	#give up after about 3 minutes
							logger.info(f"send failure {e} discarding message")
							break
			db(db.Email_Queue.id==notice.id).delete()
			continue    #until queue empty
		db.commit()
		old_now = now
		time.sleep(5)
