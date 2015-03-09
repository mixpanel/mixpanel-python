import multiprocessing
import random

from mixpanel import Mixpanel, BufferedConsumer

'''
As your application scales, it's likely you'll want to
to detect events in one place and send them somewhere
else. For example, you might write the events to a queue
to be consumed by another process.

This demo shows how you might do things, using
a custom Consumer to consume events, and a
and a BufferedConsumer to send them to Mixpanel
'''

'''
You can provide custom communication behaviors
by providing your own consumer object to the
Mixpanel constructor. Consumers are expected to
have a single method, 'send', that takes an
endpoint and a json message.
'''
class QueueWriteConsumer(object):
    def __init__(self, queue):
        self.queue = queue

    def send(self, endpoint, json_message):
        self.queue.put((endpoint, json_message))

def do_tracking(project_token, distinct_id, queue):
    '''
    This process represents the work process where events
    and updates are generated. This might be the service
    thread of a web service, or some other process that
    is mostly concerned with getting time-sensitive work
    done.
    '''
    consumer = QueueWriteConsumer(queue)
    mp = Mixpanel(project_token, consumer)
    for i in xrange(100):
        event = 'Tick'
        mp.track(distinct_id, event, {'Tick Number': i})
        print 'tick {0}'.format(i)

    queue.put(None)  # tell worker we're out of jobs

def do_sending(queue):
    '''
    This process is the analytics worker process- it can
    wait on HTTP responses to Mixpanel without blocking
    other jobs. This might be a queue consumer process
    or just a separate thread from the code that observes
    the things you want to measure.
    '''
    consumer = BufferedConsumer()
    payload = queue.get()
    while payload is not None:
        consumer.send(*payload)
        payload = queue.get()

    consumer.flush()

if __name__ == '__main__':
    # replace token with your real project token
    token = '0ba349286c780fe53d8b4617d90e2d01'
    distinct_id = ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for x in xrange(32))

    queue = multiprocessing.Queue()
    sender = multiprocessing.Process(target=do_sending, args=(queue,))
    tracker = multiprocessing.Process(target=do_tracking, args=(token, distinct_id, queue))

    sender.start()
    tracker.start()
    tracker.join()
    sender.join()
