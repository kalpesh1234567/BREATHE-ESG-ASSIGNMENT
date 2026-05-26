"""
Core models: Organization and User.
These form the multi-tenant foundation — every other record FK's back to Organization.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class Organization(models.Model):
    """
    Tenant root. Every piece of data belongs to exactly one Organization.
    Analysts only see their own org's data (enforced at the queryset level).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class User(AbstractUser):
    """
    Custom user that belongs to an Organization.
    Roles: 'analyst' can review and approve; 'admin' has full access.
    """
    ROLE_ANALYST = 'analyst'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [
        (ROLE_ANALYST, 'Analyst'),
        (ROLE_ADMIN, 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,  # superusers may have no org
        blank=True,
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)

    def __str__(self):
        return f"{self.username} ({self.organization})"
