from __future__ import division # This forces divisions to return floats, which is the default behaviour in Python 3, but not Python 2
import webapp2

## Imports from this app
from views import *

# Run Runaway!
app = webapp2.WSGIApplication( [
    ( '/'  , MainPage ),
    ( '/login', LoginHandler ),
    ( '/register', RegistrationHandler ),
    ( '/preferences', RegistrationHandler ),
    ( '/c/([^/]+)', CreateAlterTest ),
    ( '/c', CreateAlterTest ),
    ( '/add_test_group', AddTestGroup ),
    ( '/u/([^/]+)', UserProfile ),
    ( '/u', UserProfile ),
    ( '/t/([^/]+)/([tf])', OpenCloseTest ),
    ( '/t/([^/]+)', TestView ),
    ( '/t', TestView ),
    ( '/m/([^/]+)', MarkView ),
    ( '/m', MarkView ),    
    ( '/r', MarkRating ),
], debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()