import hashlib
import math
import itertools
import datetime
import logging

from google.appengine.ext import ndb
from google.appengine.datastore.datastore_query import Cursor
from google.appengine.api import users, mail, search

from models import Test, Entity, Mark

default_groups = ['python', 'javascript', 'sql', 'json']
template_dir = 'templates/'

## Helper Functions
def add_mark_to_template( template_values, in_mark ):
    """Combines Mark object properties into template_values"""
    template_values = add_entity_to_template( template_values, in_mark.marker_entity )
    # the updated_test value is required here or else the Test that is returned is the Test taken, not the current test
    updated_test = Test.query( Test.id == in_mark.test.id ).fetch(1)[0]
    template_values = add_test_to_template( template_values, updated_test )
    template_values['complete'] = in_mark.complete
    template_values['response'] = in_mark.response
    template_values['comment'] = in_mark.comment
    template_values['mark'] = in_mark.mark
    template_values['mark_id'] = in_mark.id
    template_values['mark_created'] = in_mark.created
    template_values['mark_modified'] = in_mark.modified
    template_values['rating'] = in_mark.rating
    template_values['rated'] = in_mark.rated
    return template_values

def add_entity_to_template( template_values, in_entity, request=None, open=None ):
    """Combines Entity object properties into template_values"""
    template_values['name'] = in_entity.display_name
    template_values['id'] = in_entity.id
    template_values['created'] = in_entity.created
    template_values['modified'] = in_entity.modified
    template_values['bio'] = in_entity.bio
    template_values['grouped_marks'] = get_grouped_marks_list( entity_id = in_entity.id )
    template_values['gravatar'] = "http://www.gravatar.com/avatar/" + hashlib.md5(in_entity.user.email().lower()).hexdigest() + "?s=60"
    ## Lists of Tests
    if request:
        # This might be an odd way of defining this, but I want to have to ask for these lists
        # instead of providing them to each page that loads an entity.
        entity_key = ndb.Key('Entity', template_values['id'])
        # Get cursors, if available (two won't be for sure)
        completed_cursor=Cursor(urlsafe=request.get('next_completed'))
        in_progress_cursor=Cursor(urlsafe=request.get('next_in_progress'))
        created_cursor=Cursor(urlsafe=request.get('next_created'))

        template_values['completed'] = get_marks( num=5, start_cursor=completed_cursor, ancestor_key=entity_key, mark_complete=True )
        template_values['in_progress'] = get_marks( num=5, start_cursor=in_progress_cursor, ancestor_key=entity_key, mark_complete=False )
        template_values['created_tests'] = get_tests( num=5, start_cursor=created_cursor, ancestor_key=entity_key, open=open )

    return template_values

def add_test_to_template( template_values, in_test ):
    """Combines Test object properties into template_values"""
    template_values['test_id'] = in_test.id
    template_values['title'] = in_test.title
    template_values['description'] = in_test.description
    template_values['group'] = in_test.group
    template_values['level'] = in_test.level
    template_values['test_created'] = in_test.created
    template_values['test_modified'] = in_test.modified
    template_values['author_id'] = in_test.author_id
    template_values['author_name'] = Entity.query( Entity.id == in_test.author_id ).get().display_name
    template_values['times_taken'] = in_test.times_taken
    template_values['total_score'] = in_test.total_score
    template_values['num_marked'] = in_test.num_marked
    template_values['open'] = in_test.open
    if in_test.num_marked > 0:
        template_values['average_mark'] = template_values['total_score'] / template_values['num_marked']
    mark_list = Mark.query( Mark.test.id == in_test.id ).filter( Mark.rating > -1 ).fetch()
    template_values['num_ratings'] = len(mark_list)
    if template_values['num_ratings'] > 0:
        template_values['average_rating'] =  sum([mark.rating for mark in mark_list]) / template_values['num_ratings']
        if template_values['average_rating'] is not in_test.average_rating:
            save_average_rating( in_test.id, template_values['average_rating'])
    return template_values

def save_average_rating( test_id, avg ):
    test = Test.query( Test.id == test_id ).fetch(1)[0]
    test.average_rating = avg
    test.put()
    # Add/Alter this test's Document in the search index
    doc = search.Document( doc_id = test.id, fields = [
        search.AtomField( name="group", value=test.group ),
        search.TextField( name="title", value=test.title ),
        search.NumberField( name="times_taken", value=test.times_taken ),
        search.DateField( name="date", value=test.created ),
        search.NumberField( name="level", value=test.level ),
        search.NumberField( name="rating", value=test.average_rating ),
    ])
    try:
        index = search.Index(name="tests")
        index.put( doc )
    except search.Error:
        logging.warning("Average rating failed to properly update.")
    return

def get_to_be_marked( entity, test=None, num=None ):
    """Retrieves the responses from other entities that need to have marks assigned for tests created by this entity"""
    mark_query = Mark.query( Mark.marker_entity.id == entity.id )
    mark_query = mark_query.filter( Mark.complete == False )
    if test:
        mark_query = mark_query.filter( Mark.test.id == test.id )
        mark_query = mark_query.filter( Mark.test.author_id == entity.id )

    if not num:
        return mark_query.fetch()
    else:
        return mark_query.fetch( num )

def get_marked( entity, num=None ):
    """Retrieves the responses from other entities that need to have marks assigned for tests created by this entity"""
    mark_query = Mark.query( Mark.marker_entity.id == entity.id )
    mark_query = mark_query.filter( Mark.complete == True )
    if not num:
        return mark_query.fetch()
    else:
        return mark_query.fetch( num )

def get_grouped_marks_list( entity_id ):
    """Returns a list of summary of the marks in each group
        This only provides values for groups that the user has been given
       return {{'group_name':name, 'tests_taken':tests_taken, 'total_score':num }, {...}, ... }
    """
    grouped_marks = []
    groups = set()
    mark_list = Mark.query( ancestor = ndb.Key( "Entity", entity_id) ).filter( Mark.complete == True ).order( -Mark.created ).fetch()
    for mark in mark_list:
        groups_length = len(groups)
        groups.update( mark.test.group )
        if groups_length < len(groups):
            # If the set of groups got longer, add a new dict to the list
            grouped_marks.append({
                'name': mark.test.group,
                'tests_taken': 1,
                'total_score': mark.mark * mark.test.level,
            })
        else:
            for group in grouped_marks:
                if group['name'] == mark.test.group:
                    group['tests_taken'] += 1
                    group['total_score'] += mark.mark * mark.test.level

    for group in grouped_marks:
        if group['total_score'] is not None and group['total_score'] > 0:
            group['level'] = math.floor( math.log( float(group['total_score']),2 ) )
            group['level_progress'] = (math.log( group['total_score'],2 ) - group['level']) * 100
        else:
            group['total_score'] = 0
            group['level'] = 1
            group['level_progress'] = 0
    return grouped_marks

def get_grouped_marks( entity_id ):
    """Returns a list of summary of the marks in each group
        This list will return all available lgroups, even if the level is 0.
    """
    grouped_marks = []
    groups = set()
    mark_list = Mark.query( ancestor = ndb.Key( "Entity", entity_id )).filter( Mark.complete == True ).order( -Mark.created ).fetch()
    entity = Entity.query( Entity.id == entity_id).fetch()[0]

    group_list = []
    for mark in mark_list:
        groups_length = len(groups)
        groups.update( mark.test.group )
        if groups_length < len(groups):
            # If the set of groups got longer, add a new dict to the list
            grouped_marks.append({
                'group' : mark.test.group,
                'level' : mark.test.level,
                'level_progress' : 0,
                'tests_taken' : 0,
                'total_score' : 0,
            })
        else:
            for group in grouped_marks:
                if group['group'] == mark.test.group:
                    group['tests_taken'] += 1
                    group['total_score'] += mark.mark * mark.test.level
                    group_list.append( mark.test.group )

    for group in grouped_marks:
        if group['total_score'] is not None and group['total_score'] > 0:
            group['level'] = math.floor( math.log( float(group['total_score']),2 ) )
            group['level_progress'] = (math.log( group['total_score'],2 ) - group['level']) * 100
        else:
            group['total_score'] = 0
            group['level'] = 1
            group['level_progress'] = 0

    unused_defaults = set( itertools.chain( entity.test_groups, default_groups )) - set( [ group['group'] for group in grouped_marks ] )
    for group in unused_defaults:
        grouped_marks.append( {'group':group,'level':1,'level_progress':0} )
    return grouped_marks

def get_user_group_level( level_groups, group_name ):
    for group in level_groups:
        if group['group'] == group_name:
            return group['level']
    return 1

def get_marks( num=None, start_cursor=None, ancestor_key=None, mark_complete=None):
    """Retrieves the num most recent marks, starting at start_cursor, only for the ancestor if provided, and only completed or not-completed tests if mark_complete is provided"""
    if ancestor_key:
        # This checks for only marks created by this entity
        mark_query = Mark.query( ancestor = ancestor_key ).order( -Mark.test.created )
    else:
        mark_query = Mark.query().order( -Mark.test.created )
    if mark_complete is not None:
        # Filter completed marks based on mark_complete -> default is None => all marks
        mark_query = mark_query.filter( Mark.complete == mark_complete )
    if start_cursor:
        # Set the query start to the cursor location, if provided
        marks, next_cursor, more = mark_query.fetch_page(num, start_cursor=start_cursor)
        try:
            return { 'marks':marks, 'next':next_cursor.urlsafe(), 'more':more }
        except:
            return { 'marks':marks, 'next':None, 'more':False }
    elif num:
        # Otherwise return the number of requested results
        return mark_query.fetch( num )
    # Or all if no num was specified
    return mark_query.fetch()

def get_tests( num=None, start_cursor=None, ancestor_key=None, open=None ):
    """Retrieves the num most recent tests, starting at start_cursor, and only for the ancestor if provided"""
    if ancestor_key:
        # This checks for only tests created by this entity
        test_query = Test.query( ancestor = ancestor_key ).order( -Test.created )
    else:
        test_query = Test.query().order( -Test.created )
    if open is not None:
        # filter open or closed tests as needed
        test_query = test_query.filter( Test.open == open )
    if start_cursor:
        # Set the query start to the cursor location if provided
        tests, next_cursor, more = test_query.fetch_page(num, start_cursor=start_cursor)
        try:
            return { 'tests':tests, 'next':next_cursor.urlsafe(), 'more':more }
        except:
            return { 'tests':tests, 'next':None, 'more':False }
    elif num:
        # Otherwise return the number of requested results
        return test_query.fetch( num )
    # Or all if no num was specified
    return test_query.fetch()

def get_template_values( self ):
    """Constructs and returns a dict of common values needed by all or nearly all templates"""
    user = users.get_current_user()

    template_values= {
        'date'      : datetime.datetime.now(),
        'nav_urls'  : get_navigation_urls( self, user ),
    }
    if user:
        try:
            entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            template_values['user_name'] = entity.display_name
            template_values['bio'] = entity.bio
        except:
            # User isn't an entity yet
            pass
        template_values['user'] = user
        template_values['user_id'] = user.user_id()
        template_values['nav_grav'] = "http://www.gravatar.com/avatar/" + hashlib.md5(user.email().lower()).hexdigest() + "?s=36"
    else:
        template_values['user'] = False
    return template_values

def get_navigation_urls( self, user ):
    """Constructs and returns a dict of common urls used for navigation"""
    navigation_urls = {
        'home'  : '/',
        'create_test': '/c',
        'profile': '/u',
        'tests': '/t',
    }
    if user:
        navigation_urls['logout'] = users.create_logout_url( '/' )
    else:
        navigation_urls['login'] = users.create_login_url( '/login' )
    return navigation_urls

def send_email( to, test, type ):
    """Sends an email"""
    site_name = "Densando"
    site_address = "densando-hr.appspot.com"
    address_local = "do_not_reply"
    address_suffix = "densando-hr.appspotmail.com"

    if type == "Test-Answer":
        subject = "Someone has submitted an answer to %s" % test.title
    elif type == "Answer-Response":
        subject = "Your answer to %s has been marked" % test.title

    email_message = mail.EmailMessage(
        sender = "%s <%s@%s>" % ( site_name, address_local, address_suffix ),
        subject = subject,
        to = to,
        body = subject + "\n\n" + site_address + "/t/" + test.id,
    )
    email_message.send()
    return True
