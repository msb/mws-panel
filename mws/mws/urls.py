from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import patterns, include, url
from django.contrib import admin
from sitesmanagement.views.domains import DomainListView, DomainDelete
from sitesmanagement.views.sites import SiteCreate, SiteShow, SiteList, SiteDisable, SiteDelete, SiteEdit, \
    SiteEditEmail, SiteDoNotRenew
from sitesmanagement.views.snapshots import SnapshotCreate, SnapshotDelete
from sitesmanagement.views.unixgroups import UnixGroupListView, UnixGroupCreate, UnixGroupDelete, UnixGroupUpdate
from sitesmanagement.views.vhosts import VhostListView, VhostDelete, VhostCreate, VisitVhost

urlpatterns = patterns('',
    # external apps urls
    url(r'', include('ucamwebauth.urls')),

    # admin app urls
    url(r'^admin/', include(admin.site.urls)),

    # lookup/ibis urls
    url(r'^ucamlookup/', include('ucamlookup.urls')),

    # Site management
    url(r'^$', SiteList.as_view(), name='listsites'),
    url(r'^site/new/$', SiteCreate.as_view(), name='newsite'),
    url(r'^site/show/(?P<site_id>[0-9]+)/$', SiteShow.as_view(), name='showsite'),
    url(r'^site/edit/(?P<site_id>[0-9]+)/$', SiteEdit.as_view(), name='editsite'),
    url(r'^site/email/(?P<site_id>[0-9]+)/$', SiteEditEmail.as_view(), name='editsitemail'),
    url(r'^site/delete/(?P<site_id>[0-9]+)/$', SiteDelete.as_view(), name='deletesite'),
    url(r'^site/disable/(?P<site_id>[0-9]+)/$', SiteDisable.as_view(), name='disablesite'),
    url(r'^site/donotrenew/(?P<site_id>[0-9]+)/$', SiteDoNotRenew.as_view(), name='donotrenew'),

    # Service management
    url(r'^settings/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.service_settings'),
    url(r'^billing/(?P<site_id>[0-9]+)/$', 'sitesmanagement.views.billing_management'),
    url(r'^enable/(?P<site_id>[0-9]+)/$', 'sitesmanagement.views.sites.site_enable', name='enablesite'),
    url(r'^privacy/$', 'sitesmanagement.views.privacy'),
    url(r'^vhosts/(?P<vhost_id>[0-9]+)/certificates/$', 'sitesmanagement.views.certificates'),
    url(r'^vhosts/(?P<vhost_id>[0-9]+)/generate_csr/$', 'sitesmanagement.views.generate_csr'),
    url(r'^add_domain/(?P<vhost_id>[0-9]+)/$', 'sitesmanagement.views.add_domain'),
    url(r'^set_dn_as_main/(?P<domain_id>[0-9]+)/$', 'sitesmanagement.views.set_dn_as_main'),
    url(r'^system_packages/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.system_packages'),
    url(r'^clone_vm/(?P<site_id>[0-9]+)/$', 'sitesmanagement.views.clone_vm_view'),
    url(r'^delete_vm/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.delete_vm'),
    url(r'^settings/vm/(?P<service_id>[0-9]+)/on/$', 'sitesmanagement.views.power_vm'),
    url(r'^settings/vm/(?P<service_id>[0-9]+)/reset/$', 'sitesmanagement.views.reset_vm'),
    url(r'^settings/vm/(?P<service_id>[0-9]+)/db_root_pass/$', 'sitesmanagement.views.change_db_root_password'),
    url(r'^update_os/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.update_os'),
    url(r'^backups/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.backups'),
    url(r'^apache/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.apache_modules'),
    url(r'^phplibs/(?P<service_id>[0-9]+)/$', 'sitesmanagement.views.php_libs'),

    # Vhosts management
    url(r'^vhosts/(?P<service_id>[0-9]+)/$', VhostListView.as_view(), name='listvhost'),
    url(r'^add_vhost/(?P<service_id>[0-9]+)/$', VhostCreate.as_view(), name='createvhost'),
    url(r'^vhosts/(?P<vhost_id>[0-9]+)/delete/$', VhostDelete.as_view(), name='deletevhost'),
    url(r'^visit_website/(?P<vhost_id>[0-9]+)/$', VisitVhost.as_view(), name='visitvhost'),

    # Domains management
    url(r'^domains/(?P<vhost_id>[0-9]+)/$', DomainListView.as_view(), name='listdomains'),
    url(r'^delete_domain/(?P<domain_id>[0-9]+)/$', DomainDelete.as_view(), name='deletedomain'),

    # Unix groups management
    url(r'^unix_groups/(?P<service_id>[0-9]+)/$', UnixGroupListView.as_view(), name='listunixgroups'),
    url(r'^unix_groups/(?P<service_id>[0-9]+)/add/$', UnixGroupCreate.as_view(), name='createunixgroup'),
    url(r'^unix_groups/edit/(?P<ug_id>[0-9]+)/$', UnixGroupUpdate.as_view(), name='updateunixgroup'),
    url(r'^unix_groups/delete/(?P<ug_id>[0-9]+)/$', UnixGroupDelete.as_view(), name='deleteunixgroup'),

    # Snapshot management
    url(r'^create_snapshot/(?P<service_id>[0-9]+)/$', SnapshotCreate.as_view(), name='createsnapshot'),
    url(r'^delete_snapshot/(?P<snapshot_id>[0-9]+)/$', SnapshotDelete.as_view(), name='deletesnapshot'),

    # bes++ api
    url(r'^bes/$', 'apimws.bes.bes'),

    # update snapshots
    url(r'^update_lv_list/$', 'apimws.lv.update_lv_list'),

    # apimws app
    url(r'^api/confirm_dns/(?P<dn_id>[0-9]+)/(?P<token>.+)/$', 'apimws.views.confirm_dns'),
    url(r'^api/finance/billing/$', 'apimws.views.billing_total'),
    url(r'^api/finance/billing/(?P<year>20[0-9]{2})/(?P<month>[0-9]{1,2})/$', 'apimws.views.billing_month'),
    url(r'^confirm_email/(?P<ec_id>[0-9]+)/(?P<token>(\w|\-)+)/$', 'apimws.views.confirm_email'),
    url(r'^api/post_installation/$', 'apimws.views.post_installation'),
    url(r'^api/resend_email_confirmation/(?P<site_id>[0-9]+)/$', 'apimws.views.resend_email_confirmation_view'),

    # mwsauth app
    url(r'^auth/(?P<site_id>[0-9]+)/$', 'mwsauth.views.auth_change'),
    url(r'^auth/(?P<site_id>[0-9]+)/force_update/$', 'mwsauth.views.force_update'),

    # user panel
    url(r'^user_panel/$', 'mwsauth.views.user_panel'),

    # file serve for purchase order files
   url(r'^media/billing/(?P<filename>[^/]+)$', 'sitesmanagement.views.po_file_serve'),

) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
