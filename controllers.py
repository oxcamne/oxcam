"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

    http://127.0.0.1:8000/{app_name}/{path}

If app_name == '_default' then simply

    http://127.0.0.1:8000/{path}

If path == 'index' it can be omitted:

    http://127.0.0.1:8000/

The path follows the bottlepy syntax.

@action.uses('generic.html')  indicates that the action uses the generic.html template
@action.uses(session)         indicates that the action uses the session
@action.uses(db)              indicates that the action uses the db
@action.uses(T)               indicates that the action uses the i18n & pluralization
@action.uses(auth.user)       indicates that the action requires a logged in user
@action.uses(auth)            indicates that the action requires the auth object

session, db, T, auth, and tempates are examples of Fixtures.
Warning: Fixtures MUST be declared with @action.uses({fixtures}) else your app will result in undefined behavior
"""

from py4web import action, request, abort, redirect, URL, Field, DAL
from yatl.helpers import A, HTML, P, DIV
from .common import db, session, T, cache, auth, logger, authenticated, unauthenticated, flash
from py4web.utils.grid import Grid, GridClassStyleBulma, Column
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import IS_NOT_EMPTY, IS_EMAIL
import datetime, random

"""
decorator for validating login & access permission using a one-time code
sent to email address.
Allows for an access level parameter associated with a user
for an explanation see the blog article from which I cribbed: 
    https://www.artima.com/weblogs/viewpost.jsp?thread=240845#decorator-functions-with-decorator-arguments

"""
def checkaccess(requiredaccess):
    def wrap(f):
        def wrapped_f(*args, **kwds):
            if session.get('logged_in') == True:    #logged in
                #redirect where the user wants to go
                pass
            else:
                session['url']=request.url
                redirect(URL('login'))

			#check access
            if requiredaccess != None:
                #add in access level check
                pass

            if session.get('expires'):
                if datetime.datetime.now() < session.expires:
                    pass
            return f(*args, **kwds)
        return wrapped_f
    return wrap

@action('login', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
def login():
    form = Form([Field('email', 'string',
                requires=[IS_NOT_EMPTY(), IS_EMAIL()], default = session.get('email'))],
                formstyle=FormStyleBulma)
    legend = P("Please specify your email to login, you will receive a verification email there.")
 
    if form.accepted:
        user = db(db.users.email==form.vars['email'].lower()).select().first()
        if user:
            token = str(random.randint(10000,999999))
            user.update_record(
                tokens= [token]+(user.tokens or []),
                when_issued = datetime.datetime.now(),
                url = session['url']
            )
            log = 'login '+request.remote_addr+' '+user.email+' '+request.environ['HTTP_USER_AGENT']
            logger.info(log)
            message = HTML(DIV(
                        P("Use this link to log in to David's Books."),
                        P("Please ignore this message if you did not request it."),
                        URL('validate', user.id, token, scheme=True)))
            auth.sender.send(to=user.email, subject='Confirm Email',
                             body=message)
            form = None

            legend = DIV(P('Please click the link sent to your email to continue.'),
                     P('This link is valid for 15 minutes.'))
        else:
            flash.set('Sorry, you are not authorized to view this site.')
    return locals()

@action('validate/<id:int>/<token:int>', method=['POST', 'GET'])
@action.uses(db, session)
def validate(id, token):
    user = db(db.users.id == id).select().first()
    if not user or not int(token) in user.tokens or \
        datetime.datetime.now() > user.when_issued + datetime.timedelta(minutes = 15):
        redirect(URL('index'))
    session['logged_in'] = True
    session['id'] = user.id
    session['name'] = user.name
    session['email'] = user.email
    user.update_record(tokens=[])
    log = 'verified '+request.remote_addr+' '+user.email
    logger.info(log)
    redirect(user.url)
    return locals()

@action('logout')
@action.uses(session)
def logout():
    session['logged_in'] = False
    redirect(URL('index'))

@action('index')
def index():
    redirect(URL('books_read'))

def set_book_modified(form):
    if 'id' in form.vars:   #edit rather than create
        db.Books[form.vars['id']].update_record(Modified=datetime.datetime.now())
    return dict()

@action('books_read', method=['POST', 'GET'])
@action('books_read/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session)
@checkaccess(None)
def books_read(path=None):
    grid = Grid(path,
            formstyle=FormStyleBulma, # FormStyleDefault or FormStyleBulma
            grid_class_style=GridClassStyleBulma, # GridClassStyle or GridClassStyleBulma
            query=(db.Books.id > 0), orderby=[~db.Books.Created],
            deletable=False, details=False, include_action_button_text=False,
            validation=set_book_modified,
            search_queries=[["Title", lambda value: db.Books.Title.like('%'+value+'%')],
                            ["Notes", lambda value: db.Books.Notes.like('%'+value+'%')],
                            ["> mm/dd/yyyy", lambda value: db.Books.Created>datetime.datetime.strptime(value, '%m/%d/%Y')]],   
            columns=[db.Books.Title, db.Books.Author, db.Books.Notes, db.Books.Created,
                    Column("", lambda row: A("Author", _href=URL('author_books/'+str(row.Author))))],
            )
    return dict(grid=grid, title="Books read by David")

@action('authors', method=['POST', 'GET'])
@action('authors/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session)
@checkaccess(None)
def authors(path=None):
    grid = Grid(path,
            formstyle=FormStyleBulma, # FormStyleDefault or FormStyleBulma
            grid_class_style=GridClassStyleBulma, # GridClassStyle or GridClassStyleBulma
            query=(db.Authors.id > 0), orderby=[db.Authors.Name],
            deletable=False, details=False, include_action_button_text=False,
            columns=[db.Authors.Name,
                    Column("", lambda row: A("Books", _href=URL('author_books/'+str(row.id))))],
            search_queries=[["Name", lambda value: db.Authors.Name.like('%'+value+'%')]]
            )
    return dict(grid=grid, title="List of authors read by David")

@action('author_books/<author:int>', method=['POST', 'GET'])
@action('author_books/<author:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session)
@checkaccess(None)
def author_books(author, path=None):
    title = "Books by "+db.Authors[author].Name+" read by David" 
    grid = Grid(path,
            formstyle=FormStyleBulma, # FormStyleDefault or FormStyleBulma
            grid_class_style=GridClassStyleBulma, # GridClassStyle or GridClassStyleBulma
            query=(db.Books.Author==author), orderby=[db.Books.Title],
            deletable=False, details=False, include_action_button_text=False,
            search_queries=[["Title", lambda value: db.Books.Title.like('%'+value+'%')],
                            ["Notes", lambda value: db.Books.Notes.like('%'+value+'%')]],   
            validation=set_book_modified,
            columns=[db.Books.Title, db.Books.Notes, db.Books.Created],
            )
    return dict(grid=grid, title=title)

@action("oxcam_restore", method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess(None)
def oxcam_restore():
    form = Form([Field('filespec', 'string', requires=IS_NOT_EMPTY(),
                       default='oxcam_backup.csv')], formstyle=FormStyleBulma)
    legend = P("OxCam database will be restored from this file in app base directory. Click Submit to proceed")
    
    if form.accepted:
        with open(form.vars['filespec'], 'r', encoding='utf-8', newline='') as dumpfile:
            for tablename in db.tables:	#clear out existing database
                db(db[tablename]).delete()
            db.import_from_csv_file(dumpfile, id_map={})   #, restore=True won't work in MySQL)
            flash.set("Database Restored from '"+form.vars['filespec']+"'")

    return locals()

@action("oxcam_backup")
@action.uses("message.html", db, session)
@checkaccess(None)
def oxcam_backup():
    with open('oxcam_backup.csv', 'w', encoding='utf-8', newline='') as dumpfile:
        db.export_to_csv_file(dumpfile)
    return dict(message="OxCam database backed up to 'oxcam_backup.csv' in app base directory.")

