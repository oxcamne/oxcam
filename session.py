"""
This file contains controllers used to manage the user's session
"""
from py4web import URL, request, redirect, action, Field
from .common import db, session, flash, logger, auth
from .settings import SUPPORT_EMAIL, TIME_ZONE, LETTERHEAD, SOCIETY_SHORT_NAME, PAGE_BANNER, HOME_URL, HELP_URL, DATE_FORMAT,\
		RECAPTCHA_KEY, RECAPTCHA_SECRET, VERIFY_TIMEOUT
from .models import ACCESS_LEVELS, member_name, CAT
from .utilities import email_sender
from yatl.helpers import A, H6, XML, P, DIV, INPUT
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import IS_IN_SET, IS_EMAIL, ANY_OF
from py4web.utils.factories import Inject
import datetime, random, requests

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL))

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
			if db(db.Colleges.id>0).count()==0 and not session.logged_in:
				redirect(URL('login', vars=dict(url=URL('db_restore'))))
			member_id = session.member_id
			if member_id:
				member = db(db.Members.id == member_id).select(db.Members.Access).first()
				if member:
					session.access = member.Access
			if not (session.logged_in and (not member_id or member)):    #not logged in, or member deleted
				redirect(URL('login', vars=dict(url=request.url)))

			#check access
			if requiredaccess != None:
				require = ACCESS_LEVELS.index(requiredaccess)
				have = -1
				if member_id and member.Access:
					have = ACCESS_LEVELS.index(member.Access)
				if have < require and db(db.Members.id>0).count()>0:
					redirect(URL('accessdenied'))
			return f(*args, **kwds)
		return wrapped_f
	return wrap

@action('login', method=['POST', 'GET'])
@action.uses("recaptcha_form.html", db, session, flash,
	Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL, RECAPTCHA_KEY=RECAPTCHA_KEY))
def login():
	session['logged_in'] = False
	trusted = not RECAPTCHA_KEY or db((db.users.remote_addr==request.remote_addr) & (db.users.trusted==True)).select().first() != None

	def verify_captcha(captchaData=None):
		if captchaData is None:
			return False
		data = {"secret": RECAPTCHA_SECRET, "response": captchaData}
		res = requests.post("https://www.google.com/recaptcha/api/siteverify", data=data)
		try:
			if res.json()["success"]:
				return True
		except Exception as exc:
			pass
		return False

	def validate_user_form(form):
		if trusted or verify_captcha(form.vars['g-recaptcha-response']):
			return
		if not form.errors.get('email'):
			form.errors['email'] ="Please verify you are not a robot"	

	fields = [Field('email', 'string', default=session.get('email'), requires=IS_EMAIL())]
	form = Form(fields, validation=validate_user_form, keep_values=True)
	if not trusted:
		form.structure.insert(0, INPUT(_name='g-recaptcha-response',_id='g-recaptcha-response', _hidden=True, _value='a'))

	header = P(XML(f"Please specify your email to login.<br />If you have signed in previously, please use the \
same email as this identifies your record.<br />You can change your email of record after logging in via 'My account'.<br />If \
you no longer have access to your old email, please contact {A(SUPPORT_EMAIL, _href='mailto:'+SUPPORT_EMAIL)}."))

	last = db((db.users.remote_addr==request.remote_addr)|(db.users.email==form.vars.get('email'))).select(orderby=~db.users.when_issued).first()
 
	if form.accepted:
		#rate limit the IP and email, impose 3 minute delay between login attempts
		now = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
		if not (VERIFY_TIMEOUT and last and now < last.when_issued + datetime.timedelta(minutes=VERIFY_TIMEOUT)):
			session['email'] = form.vars['email']
			redirect(URL('send_email_confirmation', vars=dict(email=form.vars['email'], url=request.query.url,
						timestamp=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None))))
		flash.set(f"<em>Please wait a bit, there is a {VERIFY_TIMEOUT} minute time-out between sending verification messages</em>", sanitize=False)
	elif last and datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) < last.when_issued + datetime.timedelta(minutes=VERIFY_TIMEOUT):
		flash.set("<em>If you didn't find your verification email, please check \
for typos in your address, and check in the spam folder.</em><br>", sanitize=False)

	return locals()

#send email confirmation message
@action('send_email_confirmation', method=['GET'])
@preferred
def send_email_confirmation():
	access = None	#for layout.html
	timestamp = request.query.get('timestamp')
	if timestamp and datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) < datetime.datetime.fromisoformat(timestamp) + datetime.timedelta(seconds=5):
		#generate email unless this is a stale re-request from a browser
		email = (request.query.get('email') or '').lower()
		if not email:	#shouldn't happen, but can be generated perhaps by safelink mechanisms?
			redirect(URL('login'))
		user = db(db.users.email==email).select().first()
		if user:
			user.update_record(remote_addr = request.remote_addr, trusted = False)
			if datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > user.when_issued + datetime.timedelta(minutes = 15):
				user.update_record(tokens=None)	#clear old expired tokens
		else:
			user = db.users[db.users.insert(email=email, remote_addr = request.remote_addr)]
		token = str(random.randint(10000,999999))
		user.update_record(tokens= [token]+(user.tokens or []),
				email = email, when_issued = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None))
		link = URL('validate', user.id, token, scheme=True, vars=dict(url=request.query.url))
		message = f"{LETTERHEAD.replace('&lt;subject&gt;', ' ')}<br><br>\
Please click {A(link, _href=link)} to continue to {SOCIETY_SHORT_NAME} \
and complete your registration or other transaction.<br><br>\
<em>If you did not initiate the request, please Reply to report this so that we can investigate</em>."
		email_sender(to=email, sender=SUPPORT_EMAIL, subject='Please Confirm Email', body=message)
	header = DIV(P("Please click the link sent to your email to continue. If you don't see the validation message, please check your spam folder."),
				P('This link is valid for 15 minutes. You may close this window.'))
	return locals()

@action('validate/<id:int>/<token:int>', method=['GET', 'POST'])
@preferred
def validate(id, token):
	user = db(db.users.id == id).select().first()
	if not user or not int(token) in user.tokens or \
			datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > user.when_issued + datetime.timedelta(minutes = 15) or \
			user.remote_addr != request.remote_addr:	#this last check may be too strong,
			#there may be configurations where the IP switches between browser and email??
		flash.set("Verification expired or from a different IP address.")
		redirect(URL('login', vars=dict(url=request.query.url)))
	user.update_record(trusted = True)
	rows = db((db.Members.id == db.Emails.Member) & db.Emails.Email.ilike(user.email)).select(
				db.Members.ALL, distinct=True)
	header = H6("Please select which of you is signing in:")
	members = [(row.id, member_name(row.id)+(' '+row.Membership+' member until '+(row.Paiddate.strftime(DATE_FORMAT) if row.Paiddate else '')  if row.Membership else '')) for row in rows]
	form = Form([Field('member', 'integer', requires=IS_IN_SET(members))],
	     formstyle=FormStyleBulma, csrf_protection=False)
	if len(rows)<=1 or 'switch_email' in request.query.url:
		member_id = rows.first().id if len(rows)==1 else None
	elif form.accepted:
		member_id = form.vars.get('member')
	else:
		return locals()	#display form
	
	session['logged_in'] = True
	session.email = user.email
	session.access = None
	session.member_id = None
	session.pay_source = None
	if member_id:
		member = db.Members[member_id]
		session.member_id = int(member_id)
		session.access = member.Access
		session.pay_source = member.Pay_source
	log =f"login verified {request.remote_addr} {user.email} {request.query.url or ''} {request.environ.get('HTTP_USER_AGENT')}"
	logger.info(log)
	redirect(request.query.url)

@action('accessdenied')
@preferred
def accessdenied():
	access = session.access	#for layout.html
	header = CAT(
			"You do not have permission for that, please contact ",
			A(SUPPORT_EMAIL, _href=f'mailto:{SUPPORT_EMAIL}'),
			" if you think this is wrong."
			)
	form = Form([], submit_value='OK')
	if form.accepted:
		redirect(URL('browser_back'))
	return locals()

@action('browser_back')
@action.uses("back.html", Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL))
def browser_back():
	return locals()

@action('logout')
@action.uses(session)
def logout():
	session['logged_in'] = False
	redirect(URL('index'))
