Welcome to Mixpanel
===================

.. automodule:: mixpanel


Primary interface
-----------------

.. autoclass:: Mixpanel
   :members:


Built-in consumers
------------------

A consumer is any object with a ``send`` method which takes two arguments: a
string ``endpoint`` name and a JSON-encoded ``message``. ``send`` is
responsible for appropriately encoding the message and sending it to the named
`Mixpanel API`_ endpoint.

:class:`~.Mixpanel` instances call their consumer's ``send`` method at the end
of each of their own method calls, after building the JSON message.

.. _`Mixpanel API`: https://mixpanel.com/help/reference/http


.. autoclass:: Consumer
   :members:

.. autoclass:: BufferedConsumer
   :members:


Handling Mixpanel outages
-------------------------

By default, :meth:`.Mixpanel.track` and the other tracking calls send their
HTTP request on the calling thread, wait for the response with no timeout,
retry 5xx responses and connection errors up to 4 times (HTTPS only), and raise
:class:`.MixpanelException` if delivery fails. During an ingestion outage this
can block your request handler and surface errors to your users. These
:class:`.Consumer` and :class:`.BufferedConsumer` options let you choose
different trade-offs:

* ``request_timeout``: seconds to wait for each attempt. The default (``None``)
  waits indefinitely, so set this in latency-sensitive code.
* ``retry_limit``: how many times to retry after the first attempt. With
  retries, a call can take up to about ``(retry_limit + 1) * request_timeout``
  plus backoff. Use ``0`` to fail after one attempt.
* ``raise_on_error=False``: log delivery failures as warnings on the
  ``mixpanel`` logger instead of raising. ``send`` returns ``False`` when a
  message could not be delivered. With :class:`.BufferedConsumer`, a batch that
  fails is dropped rather than kept in memory.

.. code-block:: python

    from mixpanel import Consumer, Mixpanel

    mp = Mixpanel(
        "YOUR_TOKEN",
        consumer=Consumer(request_timeout=2, retry_limit=1, raise_on_error=False),
    )

To keep tracking off your request path entirely, hand the calls to a
background worker. A single worker keeps events in order and avoids sharing a
consumer between threads:

.. code-block:: python

    from concurrent.futures import ThreadPoolExecutor

    tracking_executor = ThreadPoolExecutor(max_workers=1)

    tracking_executor.submit(mp.track, "user-id", "Signed Up", {"plan": "free"})

Call ``tracking_executor.shutdown(wait=True)`` before your process exits so
queued events are sent.


Exceptions
----------

.. autoexception:: MixpanelException
