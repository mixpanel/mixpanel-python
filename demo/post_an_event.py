from mixpanel import Mixpanel

def post_event(token):
    mixpanel = Mixpanel(token)
    mixpanel.track('ID', 'Script run')

if __name__ == '__main__':
    # You'll want to change this to be the token
    # from your Mixpanel project. You can find your
    # project token in the project settings dialog
    # of the Mixpanel web application
    demo_token = '391d3916270285cbf9f433f51a99a44c'
    post_event(demo_token)
