#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
this is used in PythonAnywhere environment, where it is run as a Pythonanywhere run forever task:
	py4web/py4web.py call py4web/apps oxcam.email_daemon.email_daemon
it can be run in vscode using a configuration:
		{
			"name": "Python: daily",
			"type": "python",
			"request": "launch",
			"program": "C:/Users/David/SkyDrive/py4web/py4web.py",
			"args": ["call", "apps", "oxcam.email_daemon.email_daemon"],
			"console": "integratedTerminal",
			"justMyCode": false,
		}

this is used in both test environment on PC, where it is started using email_daemon.cmd,
and in PythonAnywhere environment, where it is run as a Pythonanywhere 'run forever' task:
	py4web/py4web.py call py4web/apps oxcam.email_daemon.email_daemon
"""
import time, markmin
import os
from .common import db, auth
from .settings_private import LETTERHEAD, SOCIETY_NAME, VISIT_WEBSITE_INSTRUCTIONS
from .utilities import member_profile, event_confirm
from .models import primary_email
from .controllers import member_greeting
from py4web import URL
from yatl.helpers import HTML, XML

def email_daemon():

	path = os.path.dirname(os.path.abspath(__file__))
	print(path+' email_daemon running')

	while True:
		notice = db(db.emailqueue.id > 0).select(orderby=db.emailqueue.Created).first()
		if notice:
			bodyparts = eval(notice.bodyparts)
			select_fields = [db.Members.id]
			if 'Reservations.Member' in notice.query:	#refers to Reservation
				select_fields.append(db.Reservations.Event)
			if 'Mailings.contains'in notice.query:		#using a mailing list
				select_fields.append(db.Emails.Email)
				select_fields.append(db.Emails.id)
				bodyparts.append((f"\n\n{VISIT_WEBSITE_INSTRUCTIONS}", None))
				bodyparts.append((None, 'unsubscribe'))
			rows = db(eval(notice.query)).select(*select_fields, left=eval(notice.left) if notice.left!='' else None, distinct=True)
			for row in rows:
				body = ''
				member = db.Members[row.get(db.Members.id)]
				to = row.get(db.Emails.Email) or primary_email(member.id)
				if not to:
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
						body += markmin.markmin2html(f"\n\nThis message addressed to {notice.qdesc} [[unsubscribe {URL(f'emails/Y/{member.id}/edit/{row.get(db.Emails.id)}', scheme=True)}]]")
				auth.sender.send(to=to, sender=notice.sender, reply_to=notice.sender, bcc=notice.bcc, subject=notice.subject, body=HTML(XML(body)))
			db(db.emailqueue.id==notice.id).delete()
			continue    #until queue empty
		db.commit()
		time.sleep(5)
