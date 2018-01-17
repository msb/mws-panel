import subprocess

import datetime
import os
from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import transaction
from django.test import override_settings, TestCase
from mock import mock
from mwsauth.tests import do_test_login
from sitesmanagement.models import Site, Snapshot
from sitesmanagement.tests.tests import assign_a_site


@override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True, CELERY_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
class SnapshotsTests(TestCase):
    fixtures = [os.path.join(settings.BASE_DIR, 'sitesmanagement/fixtures/network_configuration_dev.yaml'), ]

    def setUp(self):
        do_test_login(self, user="test0001")
        assign_a_site(self)

    def test_create_snapshot(self):
        site = Site.objects.last()
        service = site.production_service
        snapshot_name = "snapshot1"
        # a get should redirect to backups page
        response = self.client.get(reverse('createsnapshot', kwargs={'service_id': service.id}))
        self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))
        self.assertEquals(Snapshot.objects.count(), 0)
        with mock.patch("apimws.utils.execute_userv_process") as mock_execute_userv_process:
            response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}),
                                        {'name': snapshot_name})
            assert_host_ansible_call(mock_execute_userv_process, service, [
                "--tags", "create_custom_snapshot", "-e", 'create_snapshot_name="%s"' % snapshot_name
            ])
        self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))
        self.assertEquals(Snapshot.objects.count(), 1)
        self.assertEquals(Snapshot.objects.first().name, snapshot_name)
        self.assertEquals(Snapshot.objects.first().service, service)
        response = self.client.get(response.url)
        self.assertContains(response, snapshot_name)
        # Try to submit non acceptable (empty) name for the snapshot
        response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}))
        self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}) +
                             "?error_message=This+field+is+required.")
        self.assertEquals(Snapshot.objects.count(), 1)
        # Try to submit non acceptable name (symbols) for the snapshot
        response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}), {'name': '-*&2/;'})
        self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}) +
                             "?error_message=Enter+a+valid+%27slug%27+consisting+of+letters%2C+numbers%2C"
                             "+underscores+or+hyphens.")
        self.assertEquals(Snapshot.objects.count(), 1)
        # Try to submit non acceptable name (symbols) for the snapshot
        with transaction.atomic():
            response = self.client.post(reverse('createsnapshot',
                                                kwargs={'service_id': service.id}), {'name': snapshot_name})
        self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}) +
                             "?error_message=Name+for+that+snapshot+already+exists")
        self.assertEquals(Snapshot.objects.count(), 1)

    def test_limit_snapshot_number(self):
        site = Site.objects.last()
        service = site.production_service
        snapshot_name = "snapshot1"
        with mock.patch("apimws.utils.execute_userv_process") as mock_execute_userv_process:
            response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}),
                                        {'name': snapshot_name})
            assert_host_ansible_call(mock_execute_userv_process, service, [
                "--tags", "create_custom_snapshot", "-e", 'create_snapshot_name="%s"' % snapshot_name
            ])
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))
            self.assertEquals(Snapshot.objects.count(), 1)
            snapshot_name = "snapshot2"
            response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}),
                                        {'name': snapshot_name})
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))
            self.assertEquals(Snapshot.objects.count(), 2)
            snapshot_name = "snapshot3"
            response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}),
                                        {'name': snapshot_name})
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}) +
                                 "?error_message=You+can+only+create+two+snapshots")
            self.assertEquals(Snapshot.objects.count(), 2)

    def test_delete_snapshot(self):
        site = Site.objects.last()
        service = site.production_service
        snapshot_name = "snapshot1"
        with mock.patch("apimws.utils.execute_userv_process") as mock_execute_userv_process:
            response = self.client.post(reverse('createsnapshot', kwargs={'service_id': service.id}),
                                        {'name': snapshot_name})
            assert_host_ansible_call(mock_execute_userv_process, service, [
                "--tags", "create_custom_snapshot", "-e", 'create_snapshot_name="%s"' % snapshot_name
            ])
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))
            self.assertEquals(Snapshot.objects.count(), 1)
            # a get should redirect to backups page
            response = self.client.get(reverse('createsnapshot', kwargs={'service_id': service.id}))
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))
            self.assertEquals(Snapshot.objects.count(), 1)
            snapshot = Snapshot.objects.first()
            response = self.client.post(reverse('deletesnapshot', kwargs={'snapshot_id': snapshot.id}))
            assert_host_ansible_call(mock_execute_userv_process, service, [
                "--tags", "delete_snapshot", "-e", 'delete_snapshot_name="%s"' % snapshot_name
            ], once=False)
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))

    def test_restore_snapshot(self):
        # We fake the start date of the site
        site = Site.objects.last()
        service = site.production_service
        new_start_date = datetime.date.today() - datetime.timedelta(days=10)
        site.start_date = new_start_date
        site.save()
        response = self.client.get(reverse('backups', kwargs={'service_id': service.id}))
        self.assertContains(response, '<input type="date" name="backupdate" id="datepicker" class="datepicker" min="' +
                            (new_start_date + datetime.timedelta(days=1)).isoformat() + '" max="' +
                            (datetime.date.today() - datetime.timedelta(days=1)).isoformat() + '" />')
        # First we try to recover an invalid date
        response = self.client.post(reverse('backups', kwargs={'service_id': service.id}),
                                    {'backupdate': (datetime.date.today() + datetime.timedelta(days=4)).isoformat()},
                                    follow=True)
        self.assertContains(response, "Incorrect date")
        self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))

        with mock.patch("sitesmanagement.views.snapshots.restore_snapshot") as mock_restore_snapshot:
            mock_restore_snapshot.delay.return_value = 0
            response = self.client.post(reverse('backups', kwargs={'service_id': service.id}),
                                        {'backupdate': (datetime.date.today() -
                                                        datetime.timedelta(days=2)).isoformat()}, follow=True)
            mock_restore_snapshot.delay.assert_called_once_with(service,
                                                                (datetime.date.today() -
                                                                 datetime.timedelta(days=2)).isoformat())
            self.assertContains(response, "Your backup is being restored")
            self.assertRedirects(response, reverse('backups', kwargs={'service_id': service.id}))

def assert_host_ansible_call(mock_subprocess, service, playbook_args, once=True):
    args = ["mws-admin", "mws_ansible_host_d", service.virtual_machines.first().network_configuration.name]
    args.extend(playbook_args)
    if once:
        mock_subprocess.assert_called_once_with(args, stderr=subprocess.STDOUT)
    else:
        mock_subprocess.assert_called_with(args, stderr=subprocess.STDOUT)
