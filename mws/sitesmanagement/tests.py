from datetime import datetime, time
import os
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings
from apimws.platforms import NoPrealocatedPrivateIPsAvailable
from mwsauth.tests import do_test_login
from models import NetworkConfig, Site, VirtualMachine, UnixGroup, Vhost
import views
from utils import is_camacuk, get_object_or_None


@override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True, CELERY_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
class SiteManagementTests(TestCase):

    def test_is_camacuk_helper(self):
        self.assertTrue(is_camacuk("www.cam.ac.uk"))
        self.assertFalse(is_camacuk("www.com.ac.uk"))

    def test_get_object_or_none(self):
        self.assertIsNone(get_object_or_None(User, username="test0001"))
        User.objects.create_user(username="test0001")
        self.assertIsNotNone(get_object_or_None(User, username="test0001"))

    def test_view_index(self):
        response = self.client.get(reverse(views.index))
        self.assertEqual(response.status_code, 302)  # Not logged in, redirected to login
        self.assertTrue(response.url.endswith(
            '%s?next=%s' % (reverse('raven_login'), reverse(views.index))))

        do_test_login(self, user="test0001")

        response = self.client.get(reverse(views.index))
        self.assertContains(response,
                            "                <p class=\"campl-notifications-icon campl-warning-icon\" "
                            "style=\"float:none; margin-bottom: 10px;\">\n                    At this moment we cannot "
                            "process any new request for a new Managed Web Server, please try again later.\n"
                            "                </p>")

        NetworkConfig.objects.create(IPv4='1.1.1.1', IPv6='::1.1.1.1', mws_domain="1.mws.cam.ac.uk")
        response = self.client.get(reverse(views.index))
        self.assertContains(response,
                            "<p><a href=\"%s\" class=\"campl-primary-cta\">Register new site</a></p>" %
                            reverse(views.new))

        site = Site.objects.create(name="testSite", institution_id="testinst", start_date=datetime.today())

        response = self.client.get(reverse(views.index))
        self.assertNotContains(response, "testSite")

        site.users.add(User.objects.get(username="test0001"))

        response = self.client.get(reverse(views.index))
        self.assertContains(response, "testSite")

    def test_view_show(self):
        response = self.client.get(reverse(views.show, kwargs={'site_id': 1}))
        self.assertEqual(response.status_code, 302)  # Not logged in, redirected to login
        self.assertTrue(response.url.endswith(
            '%s?next=%s' % (reverse('raven_login'), reverse(views.show, kwargs={'site_id': 1}))))

        do_test_login(self, user="test0001")

        response = self.client.get(reverse(views.show, kwargs={'site_id': 1}))
        self.assertEqual(response.status_code, 404)  # The Site does not exist

        site = Site.objects.create(name="testSite", institution_id="testinst", start_date=datetime.today())
        response = self.client.get(reverse(views.show, kwargs={'site_id': site.id}))
        self.assertEqual(response.status_code, 403)  # The User is not in the list of auth users

        site.users.add(User.objects.get(username="test0001"))
        response = self.client.get(reverse(views.show, kwargs={'site_id': site.id}))
        self.assertContains(response, "No Billing, please add one.")

    def test_view_new(self):
        response = self.client.get(reverse(views.new))
        self.assertEqual(response.status_code, 302)  # Not logged in, redirected to login
        self.assertTrue(response.url.endswith(
            '%s?next=%s' % (reverse('raven_login'), reverse(views.new))))

        do_test_login(self, user="test0001")

        response = self.client.get(reverse(views.new))
        self.assertEqual(response.status_code, 302)  # There aren't prealocated network configurations
        self.assertTrue(response.url.endswith(reverse(views.index)))

        NetworkConfig.objects.create(IPv4='131.111.58.255', IPv6='2001:630:212:8::8c:255',
                                     mws_domain="mws-12940.mws3.csx.cam.ac.uk", type="public")

        response = self.client.get(reverse(views.new))
        self.assertContains(response, "Request new site")

        response = self.client.post(reverse(views.new), {'siteform-description': 'Desc',
                                                         'siteform-institution_id': 'UIS',
                                                         'siteform-email': 'amc203@cam.ac.uk'})
        self.assertContains(response, "This field is required.") # Empty name, error

        response = self.client.post(reverse(views.new), {'siteform-name': 'Test Site',
                                                         'siteform-description': 'Desc',
                                                         'siteform-institution_id': 'UIS',
                                                         'siteform-email': 'amc203@cam.ac.uk'})

        test_site = Site.objects.get(name='Test Site')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse(views.show, kwargs={'site_id': test_site.id})))

        # TODO test platforms API
        # TODO test email check
        # TODO test dns api
        # TODO test errors

        self.assertEqual(test_site.email, 'amc203@cam.ac.uk')
        self.assertEqual(test_site.institution_id, 'UIS')
        self.assertEqual(test_site.description, 'Desc')

        response = self.client.get(response.url)

        self.assertContains(response, "Your email &#39;%s&#39; is still unconfirmed, please check your email inbox and "
                                      "click on the link of the email we sent you." % test_site.email )

        # Disable site
        self.assertFalse(test_site.disabled)
        while test_site.is_busy:
            time.sleep(0.25)
        response = self.client.post(reverse(views.disable, kwargs={'site_id': test_site.id}))
        # TODO test that views are restricted
        self.assertTrue(Site.objects.get(pk=test_site.id).disabled)
        #Enable site
        response = self.client.post(reverse(views.enable, kwargs={'site_id': test_site.id}))
        # TODO test that views are no longer restricted
        self.assertFalse(Site.objects.get(pk=test_site.id).disabled)

        # Clone first VM into the secondary VM
        with self.assertRaises(NoPrealocatedPrivateIPsAvailable):
            self.client.post(reverse(views.clone_vm_view, kwargs={'site_id': test_site.id}), {'primary_vm': 'true'})
        NetworkConfig.objects.create(IPv4='172.28.18.255', mws_domain="mws-08246.mws3.csx.private.cam.ac.uk",
                                     type="private")
        self.client.post(reverse(views.clone_vm_view, kwargs={'site_id': test_site.id}), {'primary_vm': 'true'})

        while test_site.secondary_vm.is_busy:
            time.sleep(0.25)
        self.client.delete(reverse(views.delete_vm, kwargs={'vm_id': test_site.secondary_vm.id}))

        test_site.delete()

    def test_view_edit(self):
        response = self.client.get(reverse(views.edit, kwargs={'site_id': 1}))
        self.assertEqual(response.status_code, 302)  # Not logged in, redirected to login
        self.assertTrue(response.url.endswith(
            '%s?next=%s' % (reverse('raven_login'), reverse(views.edit, kwargs={'site_id': 1}))))

        do_test_login(self, user="test0001")

        response = self.client.get(reverse(views.edit, kwargs={'site_id': 1}))
        self.assertEqual(response.status_code, 404)  # The Site does not exist

        site = Site.objects.create(name="testSite", institution_id="testInst", start_date=datetime.today())
        netconf = NetworkConfig.objects.create(IPv4='1.1.1.1', IPv6='::1.1.1.1', mws_domain="1.mws.cam.ac.uk")
        vm = VirtualMachine.objects.create(name="test_vm", primary=True, status="ready", site=site,
                                           network_configuration=netconf)
        response = self.client.get(reverse(views.edit, kwargs={'site_id': site.id}))
        self.assertEqual(response.status_code, 403)  # The User is not in the list of auth users

        site.users.add(User.objects.get(username="test0001"))
        response = self.client.get(reverse(views.edit, kwargs={'site_id': site.id}))
        self.assertContains(response, "Change information about your MWS")

        suspension = site.suspend_now(input_reason="test suspension")
        response = self.client.get(reverse(views.edit, kwargs={'site_id': site.id}))
        self.assertEqual(response.status_code, 403)  # The site is suspended

        suspension.active = False
        suspension.save()
        response = self.client.get(reverse(views.edit, kwargs={'site_id': site.id}))
        self.assertContains(response, "Change information about your MWS")

        self.assertNotEqual(site.name, 'testSiteChange')
        self.assertNotEqual(site.description, 'testDescChange')
        self.assertNotEqual(site.institution_id, 'UIS')
        self.assertNotEqual(site.email, 'email@change.test')
        response = self.client.post(reverse(views.edit, kwargs={'site_id': site.id}),
                                    {'name': 'testSiteChange', 'description': 'testDescChange',
                                     'institution_id': 'UIS', 'email': 'email@change.test',})
        self.assertEqual(response.status_code, 302)  # Changes done, redirecting
        self.assertTrue(response.url.endswith(reverse(views.show, kwargs={'site_id': site.id})))
        site_changed = Site.objects.get(pk=site.id)
        self.assertEqual(site_changed.name, 'testSiteChange')
        self.assertEqual(site_changed.description, 'testDescChange')
        self.assertEqual(site_changed.institution_id, 'UIS')
        self.assertEqual(site_changed.email, 'email@change.test')

        # TODO: Wait until celery tasks has finished to check the message
        #response = self.client.get(response.url)
        #self.assertContains(response, "Your email &#39;%s&#39; is still unconfirmed, please check your email inbox and "
        #                              "click on the link of the email we sent you." % site_changed.email )

    def test_view_billing(self):
        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': 1}))
        self.assertEqual(response.status_code, 302)  # Not logged in, redirected to login
        self.assertTrue(response.url.endswith(
            '%s?next=%s' % (reverse('raven_login'), reverse(views.billing_management, kwargs={'site_id': 1}))))

        do_test_login(self, user="test0001")

        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': 1}))
        self.assertEqual(response.status_code, 404)  # The Site does not exist

        site = Site.objects.create(name="testSite", institution_id="testInst", start_date=datetime.today())
        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': site.id}))
        self.assertEqual(response.status_code, 403)  # The User is not in the list of auth users

        site.users.add(User.objects.get(username="test0001"))
        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': site.id}))
        self.assertContains(response, "Change billing data")
        response = self.client.get(reverse(views.show, kwargs={'site_id': site.id}))
        self.assertContains(response, "No Billing, please add one.")

        suspension = site.suspend_now(input_reason="test suspension")
        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': site.id}))
        self.assertEqual(response.status_code, 403)  # The site is suspended

        suspension.active = False
        suspension.save()
        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': site.id}))
        self.assertContains(response, "Change billing data")

        self.assertFalse(hasattr(site, 'billing'))
        with open(os.path.join(settings.BASE_DIR, 'requirements.txt')) as fp:
            response = self.client.post(reverse(views.billing_management, kwargs={'site_id': site.id}),
                                        {'purchase_order_number': 'testOrderNumber', 'group': 'testGroup',
                                         'purchase_order': fp,})
        self.assertEqual(response.status_code, 302)  # Changes done, redirecting
        self.assertTrue(response.url.endswith(reverse(views.show, kwargs={'site_id': site.id})))
        site_changed = Site.objects.get(pk=site.id)
        self.assertEqual(site_changed.billing.purchase_order_number, 'testOrderNumber')
        self.assertEqual(site_changed.billing.group, 'testGroup')
        self.assertEqual(site_changed.billing.purchase_order.name, 'billing/requirements.txt')
        self.assertEqual(site_changed.billing.purchase_order.url, '/media/billing/requirements.txt')
        response = self.client.get(response.url)
        self.assertNotContains(response, "No Billing, please add one.")
        site_changed.billing.purchase_order.delete()

        site = Site.objects.get(pk=site.id)
        response = self.client.get(reverse(views.billing_management, kwargs={'site_id': site.id}))
        self.assertContains(response, "testOrderNumber")
        self.assertContains(response, "testGroup")
        self.assertTrue(hasattr(site, 'billing'))
        with open(os.path.join(settings.BASE_DIR, 'requirements.txt')) as fp:
            response = self.client.post(reverse(views.billing_management, kwargs={'site_id': site.id}),
                                        {'purchase_order_number': 'testOrderNumber1', 'group': 'testGroup1',
                                         'purchase_order': fp,})
        self.assertEqual(response.status_code, 302)  # Changes done, redirecting
        self.assertTrue(response.url.endswith(reverse(views.show, kwargs={'site_id': site_changed.id})))
        site_changed = Site.objects.get(pk=site.id)
        self.assertEqual(site_changed.billing.purchase_order_number, 'testOrderNumber1')
        self.assertEqual(site_changed.billing.group, 'testGroup1')
        self.assertEqual(site_changed.billing.purchase_order.name, 'billing/requirements.txt')
        self.assertEqual(site_changed.billing.purchase_order.url, '/media/billing/requirements.txt')
        response = self.client.get(response.url)
        self.assertNotContains(response, "No Billing, please add one.")
        site_changed.billing.purchase_order.delete()

    def no_permission_views_tests(site):
        pass # TODO implement calls to views where site id is the main param

    def create_site(self):
        site = Site.objects.create(name="testSite", institution_id="testInst", start_date=datetime.today())
        site.users.add(User.objects.get(username='test0001'))
        netconf = NetworkConfig.objects.create(IPv4='1.1.1.1', IPv6='::1.1.1.1', mws_domain="1.mws.cam.ac.uk")
        VirtualMachine.objects.create(name="test_vm", primary=True, status="ready", site=site,
                                      network_configuration=netconf)
        return site

    def test_unix_groups(self):
        do_test_login(self, user="test0001")
        site = self.create_site()
        response = self.client.post(reverse(views.add_unix_group, kwargs={'vm_id': site.primary_vm.id}),
                         {'unix_users': 'amc203,jw35', 'name': 'testUnixGroup'})
        response = self.client.get(response.url)
        self.assertInHTML('<td>testUnixGroup</td>', response.content)
        self.assertInHTML('<td>amc203, jw35</td>', response.content)
        unix_group = UnixGroup.objects.get(name='testUnixGroup')
        self.assertSequenceEqual([User.objects.get(username='amc203'), User.objects.get(username='jw35')],
                         unix_group.users.all())

        response = self.client.get(reverse(views.unix_group, kwargs={'ug_id': unix_group.id}))
        self.assertInHTML('<input id="id_name" maxlength="16" name="name" type="text" value="testUnixGroup" />',
                          response.content)
        self.assertContains(response, 'crsid: "amc203"')
        self.assertContains(response, 'crsid: "jw35"')

        response = self.client.post(reverse(views.unix_group, kwargs={'ug_id': unix_group.id}),
                         {'unix_users': 'jw35', 'name': 'testUnixGroup2'})
        response = self.client.get(response.url)
        self.assertInHTML('<td>testUnixGroup2</td>', response.content, count=1)
        self.assertInHTML('<td>testUnixGroup</td>', response.content, count=0)
        self.assertInHTML('<td>jw35</td>', response.content, count=1)
        self.assertInHTML('<td>amc203</td>', response.content, count=0)

    def test_vhosts_management(self):
        do_test_login(self, user="test0001")
        site = self.create_site()
        response = self.client.post(reverse(views.add_vhost, kwargs={'vm_id': site.primary_vm.id}),
                         {'name': 'testVhost'})
        response = self.client.get(response.url)  # TODO assert that url is vhost_management
        self.assertInHTML('<td>testVhost</td>', response.content)
        vhost = Vhost.objects.get(name='testVhost')
        self.assertSequenceEqual([vhost], site.primary_vm.vhosts.all())

        response = self.client.delete(reverse(views.delete_vhost, kwargs={'vhost_id': vhost.id}))
        response = self.client.get(response.url)  # TODO assert that url is vhost_management
        self.assertInHTML('<td>testVhost</td>', response.content, count=0)

    def test_domains_management(self):
        do_test_login(self, user="test0001")
        site = self.create_site()
        response = self.client.post(reverse(views.add_vhost, kwargs={'vm_id': site.primary_vm.id}),
                         {'name': 'testVhost'})
        vhost = Vhost.objects.get(name='testVhost')

        response = self.client.get(reverse(views.add_domain, kwargs={'vhost_id': vhost.id}))  # TODO check it
        response = self.client.post(reverse(views.add_domain, kwargs={'vhost_id': vhost.id}),
                                    {'name': 'test.mws3.csx.cam.ac.uk'})
        response = self.client.get(response.url)  # TODO assert that url is domains_management
        self.assertInHTML('<tbody><tr><td>test.mws3.csx.cam.ac.uk</td><td>Requested</td>'
                          '<td style="width: 135px;"><a href="#" onclick="javascript:ajax_call'
                          '(\'/set_dn_as_main/1/\', \'POST\')">Set as Master</a><a class="delete_vhost" data-toggle='
                          '"confirmation" data-href="javascript:ajax_call(\'/delete_domain/1/\', \'DELETE\')" href="#">'
                          '<i title="Delete" class="fa fa-trash-o fa-2x"></i></a></td></tr></tbody>',
                          response.content, count=1)
        self.client.get(reverse(views.set_dn_as_main, kwargs={'domain_id': 1}))
        self.assertInHTML('<tbody><tr><td>test.mws3.csx.cam.ac.uk</td><td>Requested</td>'
                          '<td style="width: 135px;"><a href="#" onclick="javascript:ajax_call'
                          '(\'/set_dn_as_main/1/\', \'POST\')">Set as Master</a><a class="delete_vhost" data-toggle='
                          '"confirmation" data-href="javascript:ajax_call(\'/delete_domain/1/\', \'DELETE\')" href="#">'
                          '<i title="Delete" class="fa fa-trash-o fa-2x"></i></a></td></tr></tbody>',
                          response.content, count=1)
        response = self.client.post(reverse(views.set_dn_as_main, kwargs={'domain_id': 1}))
        response = self.client.get(response.url)
        self.assertInHTML('<tbody><tr><td>test.mws3.csx.cam.ac.uk<br>This is the current main domain</td>'
                          '<td>Requested</td><td style="width: 135px;"><a href="#" onclick="javascript:ajax_call'
                          '(\'/set_dn_as_main/1/\', \'POST\')">Set as Master</a><a class="delete_vhost" data-toggle='
                          '"confirmation" data-href="javascript:ajax_call(\'/delete_domain/1/\', \'DELETE\')" href="#">'
                          '<i title="Delete" class="fa fa-trash-o fa-2x"></i></a></td></tr></tbody>',
                          response.content, count=1)
        response = self.client.delete(reverse(views.delete_dn, kwargs={'domain_id': 1}))
        response = self.client.get(response.url)
        self.assertInHTML('<tbody><tr><td>test.mws3.csx.cam.ac.uk<br>This is the current main domain</td>'
                          '<td>Requested</td><td style="width: 135px;"><a href="#" onclick="javascript:ajax_call'
                          '(\'/set_dn_as_main/1/\', \'POST\')">Set as Master</a><a class="delete_vhost" data-toggle='
                          '"confirmation" data-href="javascript:ajax_call(\'/delete_domain/1/\', \'DELETE\')" href="#">'
                          '<i title="Delete" class="fa fa-trash-o fa-2x"></i></a></td></tr></tbody>',
                          response.content, count=0)
        response = self.client.post(reverse(views.add_domain, kwargs={'vhost_id': vhost.id}),
                                    {'name': 'externaldomain.com'})
        response = self.client.get(response.url)
        self.assertInHTML('<tbody><tr><td>externaldomain.com<br>This is the current main domain</td><td>Accepted</td>'
                          '<td style="width: 135px;"><a href="#" onclick="javascript:ajax_call'
                          '(\'/set_dn_as_main/2/\', \'POST\')">Set as Master</a><a class="delete_vhost" data-toggle='
                          '"confirmation" data-href="javascript:ajax_call(\'/delete_domain/2/\', \'DELETE\')" href="#">'
                          '<i title="Delete" class="fa fa-trash-o fa-2x"></i></a></td></tr></tbody>',
                          response.content, count=1)
