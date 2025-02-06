"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are pages embedded in the Society's public website
"""
from py4web import action, URL
from .common import db, session
from .settings import TIME_ZONE
from yatl.helpers import H5, A, TABLE, TR, TD, CAT, XML
import datetime, markdown
from .models import primary_affiliation, event_attend
from .utilities import society_emails

#embedded in Society Past Events Page
def history_content():
	message = H5('Past Event Highlights:')
	since = datetime.datetime(2019, 3, 31)
	events = db((db.Events.DateTime < datetime.datetime.now()) & (db.Events.DateTime >= since) & \
			 ((db.Events.Page != None)|(db.Events.Details != None))).select(orderby = ~db.Events.DateTime)

	table_rows = []
	for event in events:
		table_rows.append(TR(
							TD(event.DateTime.strftime('%A, %B %d, %Y')),
							TD(A(event.Description,
				_href=URL(f"event_page/{event.id}") if event.Details else event.Page, _target='booking'))))
	message = CAT(message, TABLE(*table_rows))
	return message

@action('history', method=['GET'])
@action.uses("message_embed.html", db)
def history():
	message = history_content()
	return locals()

#embedded in Society About page
def about_content():
	def oxcamaddr(r):
		return XML(str(markdown.markdown(', '.join([f'[{e}](mailto:{e})' for e in society_emails(r.id)])))[3:-4])	#remove <p>...,</p>
			
	rows = db(db.Members.Committees.ilike('%advisory%')).select(orderby=db.Members.Lastname|db.Members.Firstname)
				
	board = rows.find(lambda r: (r.Committees or '').lower().find('board') >= 0)
	message = H5(f'Current Board Members ({len(board)}):')
	table_rows = []
	for r in board:
		table_rows.append(TR(
			TD((r.Title or '')+' '+r.Firstname+' '+r.Lastname+' '+(r.Suffix or '')),
			TD(primary_affiliation(r.id)),
			TD(oxcamaddr(r))
			))
	adv = rows.find(lambda r: (r.Committees or '').lower().find('board') < 0)
	message = CAT(message, TABLE(*table_rows),
	       			H5(f'Additional Members of the Advisory Committee ({len(adv)}):'))

	table_rows = []
	for r in adv:
		table_rows.append(TR(
			TD((r.Title or '')+' '+r.Firstname+' '+r.Lastname+' '+(r.Suffix or '')),
			TD(primary_affiliation(r.id)),
			TD(oxcamaddr(r))
			))
	pres = db(db.Members.President!=None).select(orderby=~db.Members.President)
	message = CAT(message, TABLE(*table_rows),
					H5(f'Past Presidents of the Society ({len(pres)}):'))

	table_rows = []
	for r in pres:
		table_rows.append(TR(
			TD(r.President),
			TD((r.Title or '')+' '+r.Firstname+' '+r.Lastname+' '+(r.Suffix or '')),
			TD(primary_affiliation(r.id)),
			))
	message = CAT(message, TABLE(*table_rows))
	return message

#embedded in Society About page
@action('about', method=['GET'])
@action.uses("message_embed.html", db)
def about():
	message = about_content()
	return locals()

#embedded in Society Home page and index page
def upcoming_events():
	member = db.Members[session.member_id] if session.member_id else None
	header = ''
	events = db(db.Events.DateTime>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)).select(orderby = db.Events.DateTime)
	for event in events:
		if event.AdCom_only and not (member and member.Access):
			continue
		waitlist = ' '
		savethedate = False
		if event.Booking_Closed<datetime.datetime.now(TIME_ZONE).replace(tzinfo=None):
			if event_attend(event.id):
				waitlist = ' *Booking Closed, waitlisting* '
			else:
				waitlist = ' *Save the Date* '
				savethedate = True
		elif event.Capacity and (event_attend(event.id) or 0) >= event.Capacity:
			waitlist = ' *Sold Out, waitlisting* '
		header = CAT(header, event.DateTime.strftime('%A, %B %d '), event.Description)
		if not savethedate:
			header = CAT(header, ' ', A('[register]', _href=URL(f'registration/{event.id}')))
		header = CAT(header, ' ', A('[see details]',
	 			_href=URL(f"event_page/{event.id}") if event.Details else event.Page, _target='event'), waitlist, XML('<br>'))
	return header