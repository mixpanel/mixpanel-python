from mixpanel import Mixpanel

def post_event(token):
    mixpanel = Mixpanel(token)
    mixpanel.track('ID', 'Script run')

if __name__ == '__main__':
    # You'll want to change this to be the token
    # from your Mixpanel project. You can find your
    # project token in the project settings dialog
    # of the Mixpanel web application
    demo_token = '0ba349286c780fe53d8b4617d90e2d01'
    post_event(demo_token)
