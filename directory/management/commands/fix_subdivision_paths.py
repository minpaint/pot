from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from directory.models import (
    Organization,
    StructuralSubdivision,
    Department,
    Position,
    Employee,
    Profile,
)


def _clean_part(value: str) -> str:
    return " ".join(str(value).strip().split())


def _normalize_key(value: str) -> str:
    return _clean_part(value).lower()


def _split_parts(value: str) -> list[str]:
    parts = [_clean_part(p) for p in str(value).split("/")]
    return [p for p in parts if p]


class Command(BaseCommand):
    help = "Normalize subdivisions with slashes (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--organization-id", type=int, help="Organization ID")
        parser.add_argument("--organization", type=str, help="Organization short_name_ru")
        parser.add_argument("--apply", action="store_true", help="Apply changes")
        parser.add_argument(
            "--delete-empty",
            action="store_true",
            help="Delete empty subdivisions after moving relations",
        )

    def handle(self, *args, **options):
        org_id = options.get("organization_id")
        org_short = options.get("organization")
        apply_changes = options.get("apply", False)
        delete_empty = options.get("delete_empty", False)

        organizations = Organization.objects.all()
        if org_id:
            organizations = organizations.filter(id=org_id)
        if org_short:
            organizations = organizations.filter(short_name_ru=org_short)

        if not organizations.exists():
            self.stdout.write("No organizations found for the provided filters.")
            return

        for org in organizations:
            self._process_organization(org, apply_changes, delete_empty)

    def _process_organization(self, organization, apply_changes, delete_empty):
        base_subdivisions = {
            _normalize_key(s.name): s
            for s in StructuralSubdivision.objects.filter(
                organization=organization
            ).exclude(name__contains="/")
        }
        bad_subdivisions = StructuralSubdivision.objects.filter(
            organization=organization,
            name__contains="/",
        ).order_by("name")

        if not bad_subdivisions.exists():
            self.stdout.write(f'[{organization.short_name_ru}] No subdivisions with slashes found.')
            return

        self.stdout.write(
            f'[{organization.short_name_ru}] Found {bad_subdivisions.count()} subdivisions with slashes.'
        )

        for subdivision in bad_subdivisions:
            plan = self._plan_subdivision(subdivision, base_subdivisions)
            if not plan:
                self.stdout.write(f'- Skip: "{subdivision.name}" (nothing to normalize)')
                continue

            target_subdivision, department_name, rename_to = plan
            self.stdout.write(
                f'- "{subdivision.name}" -> '
                f'subdivision="{target_subdivision.name if target_subdivision else rename_to}" '
                f'department="{department_name or "-"}"'
            )

            if not apply_changes:
                continue

            with transaction.atomic():
                target_subdivision = self._apply_plan(
                    organization,
                    subdivision,
                    target_subdivision,
                    department_name,
                    rename_to,
                    delete_empty,
                )

                # Refresh cache if the subdivision name is now a base name
                if target_subdivision and "/" not in target_subdivision.name:
                    base_subdivisions[_normalize_key(target_subdivision.name)] = target_subdivision

    def _plan_subdivision(self, subdivision, base_subdivisions):
        parts = _split_parts(subdivision.name)
        if len(parts) < 2:
            return None

        first_key = _normalize_key(parts[0])
        if first_key in base_subdivisions:
            target_subdivision = base_subdivisions[first_key]
            department_name = " / ".join(parts[1:]) if len(parts) > 1 else None
            return target_subdivision, department_name, None

        # No match for the first element: drop it
        parts = parts[1:]
        if not parts:
            return None

        target_name = parts[0]
        department_name = " / ".join(parts[1:]) if len(parts) > 1 else None
        target_subdivision = StructuralSubdivision.objects.filter(
            organization=subdivision.organization,
            name=target_name,
        ).first()

        if target_subdivision:
            return target_subdivision, department_name, None

        # Rename current subdivision
        return subdivision, department_name, target_name

    def _apply_plan(
        self,
        organization,
        source_subdivision,
        target_subdivision,
        department_name,
        rename_to,
        delete_empty,
    ):
        if rename_to and source_subdivision.name != rename_to:
            source_subdivision.name = rename_to
            source_subdivision.short_name = rename_to
            source_subdivision.save(update_fields=["name", "short_name"])

        target_subdivision = target_subdivision or source_subdivision

        department = None
        if department_name:
            department, _ = Department.objects.get_or_create(
                name=department_name,
                organization=organization,
                subdivision=target_subdivision,
                defaults={"short_name": department_name},
            )

        if target_subdivision.id != source_subdivision.id:
            self._move_departments(source_subdivision, target_subdivision)
            self._move_positions(source_subdivision, target_subdivision, department)
            self._move_employees(source_subdivision, target_subdivision, department)
            self._move_fk_relations(source_subdivision, target_subdivision)
            self._move_m2m_relations(source_subdivision, target_subdivision)

            if delete_empty and not self._has_references(source_subdivision):
                source_subdivision.delete()

        return target_subdivision

    def _move_departments(self, source_subdivision, target_subdivision):
        for department in Department.objects.filter(subdivision=source_subdivision):
            existing = Department.objects.filter(
                organization=department.organization,
                subdivision=target_subdivision,
                name=department.name,
            ).first()
            if existing:
                Position.objects.filter(department=department).update(
                    department=existing,
                    subdivision=target_subdivision,
                )
                Employee.objects.filter(department=department).update(
                    department=existing,
                    subdivision=target_subdivision,
                )
                department.delete()
            else:
                department.subdivision = target_subdivision
                department.save(update_fields=["subdivision"])

    def _move_positions(self, source_subdivision, target_subdivision, department):
        Position.objects.filter(
            subdivision=source_subdivision,
            department__isnull=True,
        ).update(
            subdivision=target_subdivision,
            department=department,
        )
        Position.objects.filter(
            subdivision=source_subdivision,
            department__isnull=False,
        ).update(
            subdivision=target_subdivision,
        )

    def _move_employees(self, source_subdivision, target_subdivision, department):
        Employee.objects.filter(
            subdivision=source_subdivision,
            department__isnull=True,
        ).update(
            subdivision=target_subdivision,
            department=department,
        )
        Employee.objects.filter(
            subdivision=source_subdivision,
            department__isnull=False,
        ).update(
            subdivision=target_subdivision,
        )

    def _move_fk_relations(self, source_subdivision, target_subdivision):
        excluded_models = {StructuralSubdivision, Department, Position, Employee}

        for model in apps.get_models():
            if model in excluded_models:
                continue
            for field in model._meta.fields:
                if field.is_relation and field.related_model == StructuralSubdivision:
                    model.objects.filter(**{field.name: source_subdivision}).update(
                        **{field.name: target_subdivision}
                    )

    def _move_m2m_relations(self, source_subdivision, target_subdivision):
        through = Profile.subdivisions.through
        subdivision_field = None
        profile_field = None

        for field in through._meta.fields:
            if field.is_relation and field.related_model == StructuralSubdivision:
                subdivision_field = field.name
            if field.is_relation and field.related_model == Profile:
                profile_field = field.name

        if not subdivision_field or not profile_field:
            return

        relations = through.objects.filter(**{subdivision_field: source_subdivision})
        for relation in relations:
            profile_id = getattr(relation, profile_field)
            if through.objects.filter(
                **{profile_field: profile_id, subdivision_field: target_subdivision}
            ).exists():
                relation.delete()
            else:
                setattr(relation, subdivision_field, target_subdivision)
                relation.save(update_fields=[subdivision_field])

    def _has_references(self, subdivision):
        if Department.objects.filter(subdivision=subdivision).exists():
            return True
        if Position.objects.filter(subdivision=subdivision).exists():
            return True
        if Employee.objects.filter(subdivision=subdivision).exists():
            return True
        if Profile.subdivisions.filter(id=subdivision.id).exists():
            return True

        for model in apps.get_models():
            for field in model._meta.fields:
                if field.is_relation and field.related_model == StructuralSubdivision:
                    if model.objects.filter(**{field.name: subdivision}).exists():
                        return True

        return False
