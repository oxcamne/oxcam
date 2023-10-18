#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This is run in it's own thread as a daemon, started by __init__.py

It also spawns the daily maintenance and backup thread at midnight local time,
in a separate thread
"""
import time, markmin, os, random, pickle, datetime
from pathlib import Path
from .common import db, auth,logger
from .settings_private import VISIT_WEBSITE_INSTRUCTIONS, TIME_ZONE
from .utilities import member_profile, event_confirm, member_greeting, emailparse
from .models import primary_email
from .daily_maintenance import daily_maintenance
from py4web import URL
from yatl.helpers import HTML, XML
from threading import Thread

def email_daemon():

	path = Path(__file__).resolve().parent.parent.parent
	os.chdir(path)		 #working directory py4web
	print(str(path)+' email_daemon running')
	old_now = None
	daily_maintenance_thread = None

	while True:
		now = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)

		if old_now and now.date()!=old_now.date(): # or\
			# (not daily_maintenance_thread and now.strftime('%H:%M')=='11:03'):
			#run the daily backup and maintenance job in its own thread
			daily_maintenance_thread = Thread(target=daily_maintenance)
			daily_maintenance_thread.start()

		notice = db(db.emailqueue.id > 0).select().first()
		if notice:
			bodyparts = emailparse(notice.body, notice.subject, notice.query)
			attachment = pickle.loads(notice.attachment) if notice.attachment else None
			select_fields = [db.Members.id]
			if 'Reservations.Event' in notice.query:	#refers to Reservation
				select_fields.append(db.Reservations.Event)
			if 'Mailings.contains'in notice.query:		#using a mailing list
				select_fields.append(db.Emails.Email)
				select_fields.append(db.Emails.id)
				bodyparts.append((VISIT_WEBSITE_INSTRUCTIONS, None))
				bodyparts.append((None, 'unsubscribe'))
			rows = db(eval(notice.query)).select(*select_fields, left=eval(notice.left) if notice.left!='' else None, distinct=True)
			#because sending may take several minutes, for fairness send in random order
			dispatch = random.sample(range(len(rows)), len(rows))
			for i in dispatch:
				row = rows[i]
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
						body += markmin.markmin2html(f"\n\nThis message addressed to {notice.qdesc} [[unsubscribe {notice.scheme}{f'emails/Y/{member.id}/select'}]]")
				retry_seconds = 2
				while True:
					try:
						auth.sender.send(to=to, subject=notice.subject, sender=notice.sender, reply_to=notice.sender,
		       				bcc=eval(notice.bcc) if notice.bcc else None, body=HTML(XML(body)), attachments=attachment)
						break
					except Exception as e:
						if retry_seconds==14:
							logger.info("email send failure - retrying")
						time.sleep(retry_seconds)
						retry_seconds += 2
						if retry_seconds==20:	#give up after about 3 minutes
							raise RuntimeError("send failure") from e
			db(db.emailqueue.id==notice.id).delete()
			continue    #until queue empty
		db.commit()
		old_now = now
		time.sleep(5)
