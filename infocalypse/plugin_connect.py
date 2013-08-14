from signal import signal, SIGINT
from time import sleep
import fcp
import threading
from mercurial import util
import sys

PLUGIN_NAME = "org.freenetproject.plugin.dvcs_webui.main.Plugin"

def connect(ui, repo):
    node = fcp.FCPNode()

    ui.status("Connecting.\n")

    # TODO: Would it be worthwhile to have a wrapper that includes PLUGIN_NAME?
    # TODO: Where to document the spec? devnotes.txt? How to format?
    hi_there = node.fcpPluginMessage(plugin_name=PLUGIN_NAME,
                                     plugin_params={'Message': 'Hello',
                                                    'VoidQuery': 'true'})[0]

    if hi_there['header'] == 'Error':
        raise util.Abort("The DVCS web UI plugin is not loaded.")

    if hi_there['Replies.Message'] == 'Error':
        # TODO: Debugging
        print hi_there
        raise util.Abort("Another VCS instance is already connected.")

    session_token = hi_there['Replies.SessionToken']

    ui.status("Connected.\n")

    def disconnect(signum, frame):
        ui.status("Disconnecting.\n")
        node.fcpPluginMessage(plugin_name=PLUGIN_NAME,
                              plugin_params=
                              {'Message': 'Disconnect',
                               'SessionToken': session_token})
        sys.exit()

    # Send Disconnect on interrupt instead of waiting on timeout.
    signal(SIGINT, disconnect)

    def ping():
        # Loop with delay.
        while True:
            pong = node.fcpPluginMessage(plugin_name=PLUGIN_NAME,
                                         plugin_params=
                                         {'Message': 'Ping',
                                          'SessionToken': session_token})[0]
            if pong['Replies.Message'] == 'Error':
                raise util.Abort(pong['Replies.Description'])
            elif pong['Replies.Message'] != 'Pong':
                ui.warn("Got unrecognized Ping reply '{0}'.\n".format(pong[
                        'Replies.Message']))

            # Wait for less than timeout threshold. In testing responses take
            # a little over a second.
            sleep(3.5)

    # Start self-perpetuating pinging in the background.
    t = threading.Timer(0.0, ping)
    # Daemon threads do not hold up the process exiting. Allows prompt
    # response to - for instance - SIGTERM.
    t.daemon = True
    t.start()

    while True:
        query_identifier = node._getUniqueId()
        # The event-querying is single-threaded, which makes things slow as
        # everything waits on the completion of the current operation.
        # Asynchronous code would require changes on the plugin side but
        # potentially have much lower latency.
        # TODO: Can wrap away PLUGIN_NAME, SessionToken, and QueryIdentifier?
        command = node.fcpPluginMessage(plugin_name=PLUGIN_NAME,
                                        plugin_params=
                                        {'Message': 'Ready',
                                         'SessionToken': session_token,
                                         'QueryIdentifier': query_identifier})[0]

        response = command['Replies.Message']
        if response == 'Error':
            raise util.Abort(command['Replies.Description'])

        if response not in handlers:
            raise util.Abort("Unsupported query '{0}'\n")

        # Handlers are indexed by the query message name, take the query
        # message, and return (result_name, plugin_params).
        result_name, plugin_params = handlers[response](command)

        plugin_params['Message'] = result_name
        plugin_params['QueryIdentifier'] = query_identifier
        plugin_params['SessionToken'] = session_token

        ack = node.fcpPluginMessage(plugin_name=PLUGIN_NAME,
                                    plugin_params=plugin_params)[0]

        if ack['Replies.Message'] != "Ack":
            raise util.Abort("Received unexpected message instead of result "
                             "acknowledgement:\n{0}\n".format(ack))


# Handlers return two items: result message name, message-specific parameters.
# The sending code handles the plugin name, required parameters and plugin name.


def VoidQuery(query):
    return "VoidResult", {}

# TODO: Perhaps look up method by name directly?
handlers = {'VoidQuery': VoidQuery}
