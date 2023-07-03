"""
This file contains controllers used to manage the user's session
"""
from py4web import URL, request, redirect, action, Field, response
from .common import db, session, flash, logger
from .settings import SUPPORT_EMAIL, TIME_ZONE
from .models import ACCESS_LEVELS, member_name
from yatl.helpers import A, H6, XML, P
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import IS_IN_SET, IS_NOT_EMPTY, IS_EMAIL
import datetime

"""
decorator for validating login & access permission using a one-time code
sent to email address.
Allows for an access level parameter associated with a user
for an explanation see the blog article from which I cribbed 
	https://www.artima.com/weblogs/viewpost.jsp?thread=240845#decorator-functions-with-decorator-arguments

"""
def checkaccess(requiredaccess):
	def wrap(f):
		def wrapped_f(*args, **kwds):
			session['url_prev'] = session.get('url')
			session['url']=request.url
			if session.get('back') and len(session['back'])>0 and request.url==session['back'][-1]:
				session['back'].pop()
			if not session.get('logged_in') == True:    #logged in
				if db(db.Members.id>0).count()==0:
					session['url']=URL('db_restore')
				redirect(URL('login'))

			#check access
			if requiredaccess != None:
				require = ACCESS_LEVELS.index(requiredaccess)
				if not session.get('member_id') or not session.get('access'):
					if db(db.Members.id>0).count()==0:
						return f(*args, **kwds)
				have = ACCESS_LEVELS.index(session['access']) if session.get('access') != None else -1
				if have < require:
					redirect(URL('accessdenied'))
			return f(*args, **kwds)
		return wrapped_f
	return wrap

@action('login', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
def login():
	user = db(db.users.remote_addr==request.remote_addr).select().first()
	form = Form([Field('email', 'string',
				requires=[IS_NOT_EMPTY(), IS_EMAIL()],
				default = user.email if user else session.get('email'))],
				formstyle=FormStyleBulma)
	header = P(XML(f"Please specify your email to login.<br />If you have signed in previously, please use the \
same email as this identifies your record.<br />You can change your email after logging in via 'My account'.<br />If \
you no longer have access to your old email, please contact {A(SUPPORT_EMAIL, _href='mailto:'+SUPPORT_EMAIL)}."))
 
	if form.accepted:
		log =f"login {request.remote_addr} {request.environ['HTTP_USER_AGENT']} {form.vars['email']} {session.get('url') or ''}"
		logger.info(log)
		redirect(URL('send_email_confirmation', vars=dict(email=form.vars['email'])))
	return locals()

@action('validate/<id:int>/<token:int>', method=['GET', 'POST'])
@action.uses("gridform.html", db, session)
def validate(id, token):
	user = db(db.users.id == id).select().first()
	if not user or not int(token) in user.tokens or \
			datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > user.when_issued + datetime.timedelta(minutes = 15):
			#user.remote_addr != request.remote_addr:	#this check may be too strong,
			#there may be configurations where the IP switches between browser and email??
		redirect(URL('index'))
	rows = db((db.Members.id == db.Emails.Member) & db.Emails.Email.ilike(user.email)).select(
				db.Members.ALL, distinct=True)
	header = H6("Please select which of you is signing in:")
	members = [(row.id, member_name(row.id)+(' '+row.Membership+' member until '+(row.Paiddate.strftime('%m/%d/%Y') if row.Paiddate else '')  if row.Membership else '')) for row in rows]
	form = Form([Field('member', 'integer', requires=IS_IN_SET(members))],
	     formstyle=FormStyleBulma)
	if len(rows)<=1 or 'switch_email' in user.url:
		member_id = rows.first().id if len(rows)==1 else None
	elif form.vars.get('member'):
		#note, if we use form.accepted the user will have to click twice;
		#apparently when validate is invoked from another site (e.g. gmail) a new form_key
		#is put in the response cookie, but won't match the proper key, in other words we
		#run into CSRF protection.
		member_id = form.vars.get('member')
	else:
		return locals()	#display form
	
	session['logged_in'] = True
	session['email'] = user.email
	session['filter'] = None
	session['access'] = None
	session['member_id'] = 0
	session['back'] = []
	if member_id:
		session['member_id'] = int(member_id)
		session['access'] = db.Members[member_id].Access
	log = 'verified '+request.remote_addr+' '+user.email
	logger.info(log)
	user.update_record(tokens=[])
	redirect(user.url)

@action('accessdenied')
@action.uses(session, flash)
def accessdenied():
	flash.set(f"You do not have permission for that, please contact {SUPPORT_EMAIL} if you think this is wrong")
	redirect(session['url_prev'])
	return locals()

@action('logout')
@action.uses(session)
def logout():
	session['logged_in'] = False
	redirect(URL('index'))
