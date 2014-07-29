import datetime
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from apimws.utils import email_confirmation, platforms_api_request, ip_register_api_request
from sitesmanagement.utils import is_camacuk
from .models import SiteForm, DomainNameFormNewSite, Site, BillingForm, DomainName, NetworkConfig, EmailConfirmation


@login_required
def index(request):
    if NetworkConfig.num_pre_allocated() < 1:
        deactivate_new = True
    else:
        deactivate_new = False
    all_sites = request.user.sites.all().order_by('name')
    return render(request, 'index.html', {
        'all_sites': all_sites,
        'deactivate_new': deactivate_new
    })


@login_required
def new(request):
    if NetworkConfig.num_pre_allocated() < 1:
        return HttpResponseRedirect(reverse('sitesmanagement.views.index')) #TODO redirect to some error message

    breadcrumbs = {}
    breadcrumbs[0] = dict(name='New Manage Web Server', url=reverse(new))

    # TODO: FIX: if SiteForm's name field is empty then DomainNameForm errors are also shown
    if request.method == 'POST':  # If the form has been submitted...
        site_form = SiteForm(request.POST, prefix="siteform", user=request.user) # A bound form
        domain_form = DomainNameFormNewSite(request.POST, prefix="domainform")
        if site_form.is_valid() and domain_form.is_valid():

            site = site_form.save(commit=False)
            site.start_date = datetime.date.today()
            site.save()

            # Save user that requested the site
            site.users.add(request.user)

            try:
                platforms_api_request(site, primary=True) #TODO do it after saving a site
            except Exception as e:
                raise e # TODO try again later. pass to celery?

            try:
                # Check domain name requested
                domain_requested = domain_form.save(commit=False)
                if domain_requested.name != '':  #TODO do it after saving a domain request
                    if is_camacuk(domain_requested.name):
                        ip_register_api_request(site, domain_requested.name)
                    else:
                        site.main_domain = DomainName.objects.create(name=domain_requested.name, status='accepted', site=site)
                        site.save()
            except Exception as e:
                raise e # TODO try again later. pass to celery?

            try:
                if site.email:
                    email_confirmation(site) #TODO do it after saving a site
            except Exception as e:
                raise e # TODO try again later. pass to celery?

            return HttpResponseRedirect(reverse('sitesmanagement.views.show', kwargs={'site_id': site.id}))  # Redirect after POST
    else:
        site_form = SiteForm(prefix="siteform", user=request.user)  # An unbound form
        domain_form = DomainNameFormNewSite(prefix="domainform")

    return render(request, 'mws/new.html', {
        'site_form': site_form,
        'domain_form': domain_form,
        'breadcrumbs': breadcrumbs
    })


@login_required
def edit(request, site_id):
    site = get_object_or_404(Site, pk=site_id)

    if not site in request.user.sites.all():
        return HttpResponseForbidden()

    if site.is_admin_suspended():
        return HttpResponseForbidden()

    breadcrumbs = {}
    breadcrumbs[0] = dict(name='Manage Web Server: '+str(site.name), url=reverse(show, kwargs={'site_id': site.id}))
    breadcrumbs[1] = dict(name='Change information about your MWS',
                          url=reverse('sitesmanagement.views.edit', kwargs={'site_id': site.id}))

    if request.method == 'POST':
        site_form = SiteForm(request.POST, user=request.user, instance=site)
        if site_form.is_valid():
            site_form.save()
            return HttpResponseRedirect(reverse('sitesmanagement.views.show', kwargs={'site_id': site.id}))  # Redirect after POST
    else:
        site_form = SiteForm(user=request.user, instance=site)

    return render(request, 'mws/edit.html', {
        'site_form': site_form,
        'site': site,
        'breadcrumbs': breadcrumbs
    })


@login_required
def show(request, site_id):
    site = get_object_or_404(Site, pk=site_id)

    if not site in request.user.sites.all():
        return HttpResponseForbidden()

    if site.is_admin_suspended():
        return HttpResponseForbidden()

    breadcrumbs = {}
    breadcrumbs[0] = dict(name='Manage Web Server: '+str(site.name), url=reverse(show, kwargs={'site_id': site.id}))

    warning_messages = []

    for domain_name in site.domain_names.all():
        if domain_name.status == 'requested':
            warning_messages.append("Your domain name %s has been requested and is under review." % domain_name.name)

    if not hasattr(site, 'billing'):
        warning_messages.append("No Billing, please add one.")

    if site.email:
        site_email = EmailConfirmation.objects.get(email=site.email, site_id=site.id)
        if site_email.status == 'pending':
            warning_messages.append("Your email is still unconfirmed, please click on the link of the sent email")

    if site.primary_vm().status != 'ready':
        warning_messages.append("Your Manage Web Server is being prepared")

    return render(request, 'mws/show.html', {
        'breadcrumbs': breadcrumbs,
        'warning_messages': warning_messages,
        'site': site
    })


@login_required
def billing(request, site_id):
    site = get_object_or_404(Site, pk=site_id)

    if not site in request.user.sites.all():
        return HttpResponseForbidden()

    if site.is_admin_suspended():
        return HttpResponseForbidden()

    breadcrumbs = {}
    breadcrumbs[0] = dict(name='Manage Web Server: '+str(site.name), url=reverse(show, kwargs={'site_id': site.id}))
    #TODO Change this
    breadcrumbs[1] = dict(name='Billing', url=reverse(show, kwargs={'site_id': site.id}))

    if request.method == 'POST':  # If the form has been submitted...
        if hasattr(site, 'billing'):
            billing_form = BillingForm(request.POST, request.FILES, instance=site.billing) # A bound form
            if billing_form.is_valid():
                billing_form.save()
                return HttpResponseRedirect(reverse('sitesmanagement.views.show', kwargs={'site_id': site.id}))  # Redirect after POST
        else:
            billing_form = BillingForm(request.POST, request.FILES) # A bound form
            if billing_form.is_valid():
                billing = billing_form.save(commit=False)
                billing.site = site
                billing.save()
                return HttpResponseRedirect(reverse('sitesmanagement.views.show', kwargs={'site_id': site.id}))  # Redirect after POST
    elif hasattr(site, 'billing'):
        billing_form = BillingForm(instance=site.billing)
    else:
        billing_form = BillingForm()  # An unbound form

    return render(request, 'mws/billing.html', {
        'breadcrumbs': breadcrumbs,
        'site': site,
        'billing_form': billing_form
    })


def privacy(request):
    return render(request, 'index.html', {})


@login_required
def domains_management(request, site_id):
    site = get_object_or_404(Site, pk=site_id)

    if not site in request.user.sites.all():
        return HttpResponseForbidden()

    if site.is_admin_suspended():
        return HttpResponseForbidden()

    breadcrumbs = {}
    breadcrumbs[0] = dict(name='Manage Web Server: '+str(site.name), url=reverse(show, kwargs={'site_id': site.id}))
    breadcrumbs[1] = dict(name='Domains Management', url=reverse(domains_management, kwargs={'site_id': site.id}))


    return render(request, 'mws/domains.html', {
        'breadcrumbs': breadcrumbs,
        'site': site
    })


@login_required
def set_dn_as_main(request, site_id, domain_id):
    site = get_object_or_404(Site, pk=site_id)
    domain = get_object_or_404(DomainName, pk=domain_id)

    if (site not in request.user.sites.all()) or (domain not in site.domain_names.all()):
        return HttpResponseForbidden()

    if site.is_admin_suspended():
        return HttpResponseForbidden()

    site.main_domain = domain
    site.save()

    return HttpResponseRedirect(reverse('sitesmanagement.views.domains_management', kwargs={'site_id': site.id}))