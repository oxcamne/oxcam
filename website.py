"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are pages embedded in the Society's public website
"""
from py4web import action, URL, request
from .common import db, session
from .settings import TIME_ZONE
from yatl.helpers import H5, A, TABLE, TR, TD, CAT, XML, EM
import datetime, markdown
from .models import primary_affiliation, event_attend
from .utilities import society_emails

#embedded in Society Recent Events Page
def history_content():
	since = datetime.datetime(2019, 3, 31)
	events = db((db.Events.DateTime < datetime.datetime.now()) & (db.Events.DateTime >= since) & \
			 ((db.Events.Page != None)|(db.Events.Details != None)) & \
				(db.Events.AdCom_only==False)).select(orderby = ~db.Events.DateTime)

	table_rows = []
	for event in events:
		table_rows.append(TR(
							TD(event.DateTime.strftime('%A, %B %d, %Y')),
							TD(A(event.Description, _href=URL(f"event_page/{event.id}") \
								if event.Details else event.Page, _target='booking'))))
		if event.Speaker:
			table_rows.append(TR(TD(''), TD(event.Speaker)))
	message = TABLE(*table_rows)
	return message

@action('history', method=['GET'])
@action.uses("message_embed.html", db)
def history():
	message = history_content()
	return locals()

#embedded in Society About page
def about_content(board_name='', committee_name=''):
	def oxcamaddr(r):
		return XML(str(markdown.markdown(', '.join([f'[{e}](mailto:{e})' for e in society_emails(r.id)])))[3:-4])	#remove <p>...,</p>

	message = ''
	if board_name:
		board_pattern = f"%{board_name}%"
		board = db(db.Members.Committees.ilike(board_pattern)).select(orderby=db.Members.Lastname|db.Members.Firstname)
		if board:
			message = H5(f'{board_name} Members ({len(board)}):')
			table_rows = []
			for r in board:
				table_rows.append(TR(
					TD((r.Title or '')+' '+r.Firstname+' '+r.Lastname+' '+(r.Suffix or '')),
					TD(primary_affiliation(r.id)),
					TD(oxcamaddr(r))
					))
			message = CAT(message, TABLE(*table_rows))
	
	if committee_name:
		committee_pattern = f"%{committee_name}%"
		committee = db(db.Members.Committees.ilike(committee_pattern) & ~db.Members.Committees.ilike(board_pattern)).select(orderby=db.Members.Lastname|db.Members.Firstname)
		if committee:
			message = CAT(message, H5(f'Additional {committee_name} Members ({len(committee)}):'))
			table_rows = []
			for r in committee:
				table_rows.append(TR(
					TD((r.Title or '')+' '+r.Firstname+' '+r.Lastname+' '+(r.Suffix or '')),
					TD(primary_affiliation(r.id)),
					TD(oxcamaddr(r))
					))
			message = CAT(message, TABLE(*table_rows))

	pres = db(db.Members.President!=None).select(orderby=~db.Members.President)
	if pres:
		message = CAT(message, H5(f'Past Presidents of the Society ({len(pres)}):'))
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
	message = about_content(board_name=request.query.get('board', ''), committee_name=request.query.get('committee', ''))
	return locals()

#embedded in Society Home page and index page
def upcoming_events():
	member = db.Members[session.member_id] if session.member_id else None
	header = ''
	events = db(db.Events.DateTime>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)).select(orderby = db.Events.DateTime)
	if not events:
		return CAT(header, XML(markdown.markdown('Please check again soon!')[3:-4]+'<br>'))
	for event in events:
		if event.AdCom_only and not (member and member.Access):
			continue
		attend = event_attend(event.id)
		line = f"{event.DateTime.strftime('%A, %B %d ')} **[{event.Description}]({URL(f'event_page/{event.id}') if event.Details else event.Page})**".strip()
		if event.Booking_Closed<datetime.datetime.now(TIME_ZONE).replace(tzinfo=None):
			if not attend:
				line = f"{event.DateTime.strftime('%A, %B %d ')} **{event.Description.strip()}** *Save the Date*"
			else:
				line += ' *Booking Closed, waitlisting*'
		else:
			url = URL(f"registration/{event.id}")
			line+= f" register **[here]({url})**"
			if event.Capacity and (attend or 0) >= event.Capacity:
				line +=' *Sold Out, waitlisting*'
		header = CAT(header, XML(markdown.markdown(line)[3:-4]+'<br>'))
	return header

@action('calendar', method=['GET'])
@action.uses("message_embed.html", db)
def calendar():
	message = upcoming_events()
	return locals()
