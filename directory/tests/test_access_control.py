from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from directory.models import Department, Organization, StructuralSubdivision
from directory.utils.permissions import AccessControlHelper


def obj(org=None, sub=None, dep=None):
    """Заглушка объекта с атрибутами, по которым can_access_object проверяет права (как у Employee/Equipment)."""
    return SimpleNamespace(organization=org, subdivision=sub, department=dep)


def make_org(suffix):
    return Organization.objects.create(
        full_name_ru=f'Организация {suffix}',
        short_name_ru=f'Орг{suffix}',
        full_name_by=f'Арганізацыя {suffix}',
        short_name_by=f'Арг{suffix}',
    )


class AccessControlHelperTests(TestCase):
    def setUp(self):
        self.org1 = make_org('1')
        self.org2 = make_org('2')
        self.sub1 = StructuralSubdivision.objects.create(name='Цех 1', organization=self.org1)
        self.sub1b = StructuralSubdivision.objects.create(name='Цех 1б', organization=self.org1)
        self.sub2 = StructuralSubdivision.objects.create(name='Цех 2', organization=self.org2)
        self.dep1 = Department.objects.create(name='Отдел 1', organization=self.org1, subdivision=self.sub1)
        self.dep1b = Department.objects.create(name='Отдел 1б', organization=self.org1, subdivision=self.sub1b)
        self.user = User.objects.create_user('u', password='p')

    def test_superuser_sees_everything(self):
        admin = User.objects.create_superuser('admin', 'a@a.a', 'p')
        self.assertEqual(AccessControlHelper.get_accessible_organizations(admin).count(), 2)
        self.assertTrue(AccessControlHelper.can_access_object(admin, obj(sub=self.sub2)))
        self.assertEqual(AccessControlHelper.get_user_access_level(admin), 'superuser')

    def test_anonymous_has_no_organizations(self):
        orgs = AccessControlHelper.get_accessible_organizations(AnonymousUser())
        self.assertEqual(orgs.count(), 0)

    def test_user_without_access(self):
        self.assertEqual(AccessControlHelper.get_accessible_organizations(self.user).count(), 0)
        self.assertFalse(AccessControlHelper.can_access_object(self.user, obj(org=self.org1, sub=self.sub1, dep=self.dep1)))
        self.assertEqual(AccessControlHelper.get_user_access_level(self.user), 'none')

    def test_organization_access_covers_children(self):
        self.user.profile.organizations.add(self.org1)
        can = AccessControlHelper.can_access_object
        self.assertTrue(can(self.user, obj(org=self.org1)))
        self.assertTrue(can(self.user, obj(sub=self.sub1)))
        self.assertTrue(can(self.user, obj(org=self.org1, sub=self.sub1, dep=self.dep1)))
        self.assertFalse(can(self.user, obj(org=self.org2)))
        self.assertFalse(can(self.user, obj(sub=self.sub2)))
        self.assertEqual(AccessControlHelper.get_user_access_level(self.user), 'organization')

    def test_subdivision_access_is_limited_to_its_departments(self):
        self.user.profile.subdivisions.add(self.sub1)
        can = AccessControlHelper.can_access_object
        self.assertTrue(can(self.user, obj(sub=self.sub1)))
        self.assertTrue(can(self.user, obj(org=self.org1, sub=self.sub1, dep=self.dep1)))
        self.assertFalse(can(self.user, obj(sub=self.sub1b)))
        self.assertFalse(can(self.user, obj(org=self.org1, sub=self.sub1b, dep=self.dep1b)))
        self.assertEqual(AccessControlHelper.get_user_access_level(self.user), 'subdivision')

    def test_department_access_is_only_that_department(self):
        self.user.profile.departments.add(self.dep1)
        can = AccessControlHelper.can_access_object
        self.assertTrue(can(self.user, obj(org=self.org1, sub=self.sub1, dep=self.dep1)))
        self.assertFalse(can(self.user, obj(org=self.org1, sub=self.sub1b, dep=self.dep1b)))
        self.assertFalse(can(self.user, obj(sub=self.sub1)))
        self.assertEqual(AccessControlHelper.get_user_access_level(self.user), 'department')

    def test_accessible_orgs_derived_from_subdivision_access(self):
        self.user.profile.subdivisions.add(self.sub2)
        orgs = AccessControlHelper.get_accessible_organizations(self.user)
        self.assertEqual(list(orgs), [self.org2])
