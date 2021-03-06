MWS Control Panel Web Application
=================================

The Managed Web Service panel is a Django web application which provides the
primary user-facing interface to the MWS.

.. toctree::
    :hidden:

    gettingstarted
    vmlifecycle
    sitesmanagement
    api

The documentation for the panel is broken into a number of sections:

:any:`gettingstarted`
    Information for new developers on how to clone and run a local development
    version of the panel application.
:any:`vmlifecycle`
    A description of the "lifecycle" of the VMs we manage from preallocation
    through assignment to a user. The lifecycle of the VMs is entirely managed
    by the panel application

The panel is implemented as Django applications:

:any:`sitesmanagement`
    The ``sitesmanagement`` application contains the bulk of the control panel.
:any:`api`
    The ``apimws`` application implements API endpoints intended to be called by
    other parts of the MWS infrastructure.
