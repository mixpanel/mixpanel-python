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


Exceptions
----------

.. autoexception:: MixpanelException
