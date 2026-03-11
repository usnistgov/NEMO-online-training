from datetime import timedelta

from NEMO.models import EmailLog, User, UserType
from NEMO.tests.test_utilities import NEMOTestCaseMixin
from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from NEMO_online_training.models import OnlineTraining, OnlineTrainingAction, OnlineUserTraining, ProspectiveUser
from NEMO_online_training.training_actions import action_handlers
from NEMO_online_training.utilities import ONLINE_TRAINING_ACTION_EXTEND_ACCESS, ONLINE_TRAINING_ACTION_SEND_EMAIL


class OnlineTrainingTest(NEMOTestCaseMixin, TestCase):

    def setUp(self):
        # Create user types
        self.staff_type = UserType.objects.create(name="Staff", display_order=1)
        self.student_type = UserType.objects.create(name="Student", display_order=2)
        self.technician_type = UserType.objects.create(name="Technician", display_order=3)

        # Create NEMO users of different types
        self.staff_user = User.objects.create(
            username="staff",
            first_name="Staff",
            last_name="User",
            email="staff@nemo.com",
            type=self.staff_type,
        )
        self.student_user = User.objects.create(
            username="student",
            first_name="Student",
            last_name="User",
            email="student@nemo.com",
            type=self.student_type,
        )

        self.prospective_staff = ProspectiveUser.create_from_nemo_user(self.staff_user)
        self.prospective_student = ProspectiveUser.create_from_nemo_user(self.student_user)
        self.prospective_only = ProspectiveUser.objects.create(
            first_name="Prospective", last_name="User", email="prospective@nemo.com"
        )

        self.training = OnlineTraining.objects.create(name="Test Training", completion_time_limit=120, enabled=True)

    def test_plugin_is_installed(self):
        assert apps.is_installed("NEMO_online_training")

    def test_extend_access_all_nemo_users(self):
        """Test that extend access action applies to all NEMO users when 'all_nemo' is selected."""
        # Create action for all NEMO users
        action = OnlineTrainingAction.objects.create(
            online_training=self.training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 365},
            user_filter="all_nemo",  # All NEMO users
        )
        action.full_clean()

        # Set initial access expiration dates
        initial_date = timezone.now()
        self.staff_user.access_expiration = initial_date
        self.student_user.access_expiration = initial_date
        self.staff_user.save()
        self.student_user.save()

        # Test that action applies to all NEMO users
        self.assertTrue(action.applies_to_user(self.prospective_staff))
        self.assertTrue(action.applies_to_user(self.prospective_student))
        self.assertFalse(action.applies_to_user(self.prospective_only))

        # Perform action for staff user
        user_training_staff = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_staff
        )
        action_handlers[action.action_type].perform(action, user_training_staff)

        # Verify access was extended
        self.staff_user.refresh_from_db()
        expected_date = initial_date + timedelta(days=365)
        self.assertEqual(self.staff_user.access_expiration, expected_date.date())

        # Perform action for student user
        user_training_student = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_student
        )
        action_handlers[action.action_type].perform(action, user_training_student)

        # Verify access was extended
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.access_expiration, expected_date.date())

    def test_extend_access_specific_user_types(self):
        """Test that extend access action applies only to specific user types."""
        # Create action for staff and technician only
        action = OnlineTrainingAction.objects.create(
            online_training=self.training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 180},
            user_filter=f"{self.staff_type.id},{self.technician_type.id}",  # Staff and Technician only
        )
        action.full_clean()

        # Set initial access expiration dates
        initial_date = timezone.now()
        self.staff_user.access_expiration = initial_date
        self.student_user.access_expiration = initial_date
        self.staff_user.save()
        self.student_user.save()

        # Test that action applies to staff and technician, but not student
        self.assertTrue(action.applies_to_user(self.prospective_staff))
        self.assertFalse(action.applies_to_user(self.prospective_student))
        self.assertFalse(action.applies_to_user(self.prospective_only))

        # Perform action for staff user
        user_training_staff = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_staff
        )
        action_handlers[action.action_type].perform(action, user_training_staff)

        # Verify staff access was extended
        self.staff_user.refresh_from_db()
        expected_date = initial_date + timedelta(days=180)
        self.assertEqual(self.staff_user.access_expiration, expected_date.date())

        # Perform action for student user
        user_training_student = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_student
        )
        action_handlers[action.action_type].perform(action, user_training_student)

        # Student's access should not have changed
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.access_expiration, initial_date.date())

    def test_extend_access_prospective_users_only(self):
        """Test that extend access action only for prospective users fails."""
        action = OnlineTrainingAction.objects.create(
            online_training=self.training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 90},
            user_filter="prospective",  # Prospective users only
        )
        # Should raise a validation error because prospective users are not allowed to have access expiration
        self.assertRaises(ValidationError, action.full_clean)

    def test_extend_access_combined_filter(self):
        """Test that extend access action applies to specific types AND prospective users."""
        # Create action for staff type + prospective users
        action = OnlineTrainingAction.objects.create(
            online_training=self.training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 30},
            user_filter=f"{self.staff_type.id},prospective",  # Staff + prospective
        )
        # Should raise a validation error because prospective users are not allowed to have access expiration
        self.assertRaises(ValidationError, action.full_clean)

    def test_extend_access_empty_filter(self):
        """Test that action with an empty filter doesn't pass validation."""
        action = OnlineTrainingAction.objects.create(
            online_training=self.training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 365},
            user_filter="",  # Empty filter
        )
        # Should raise a validation error because an empty filter is not allowed
        self.assertRaises(ValidationError, action.full_clean)

    def test_email_prospective_users_only(self):
        """Test that email access action applies only to prospective users."""
        action = OnlineTrainingAction.objects.create(
            online_training=self.training,
            action_type=ONLINE_TRAINING_ACTION_SEND_EMAIL,
            configuration={
                "subject": "Training Completion Reminder",
                "message": "Dear {{ user.first_name }}, please complete the training.",
                "recipients": ["user"],
            },
            user_filter="prospective",  # Prospective users only
        )
        action.full_clean()

        # Test that action applies only to prospective user without NEMO account
        self.assertFalse(action.applies_to_user(self.prospective_staff))
        self.assertFalse(action.applies_to_user(self.prospective_student))
        self.assertTrue(action.applies_to_user(self.prospective_only))

        email_count = EmailLog.objects.count()
        user_training_student = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_student
        )
        action_handlers[action.action_type].perform(action, user_training_student)
        self.assertEqual(EmailLog.objects.count(), email_count)
        user_training_staff = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_staff
        )
        action_handlers[action.action_type].perform(action, user_training_staff)
        self.assertEqual(EmailLog.objects.count(), email_count)
        user_training_prospective = OnlineUserTraining.objects.create(
            online_training=self.training, prospective_user=self.prospective_only
        )
        action_handlers[action.action_type].perform(action, user_training_prospective)
        self.assertEqual(EmailLog.objects.count(), email_count + 1)

    def test_self_enrollment_training_with_action(self):
        """Test that a user can self-enroll in a training and actions are triggered upon completion."""
        from django.core.signing import TimestampSigner
        from django.urls import reverse

        from NEMO_online_training.models import OnlineUserTraining

        # Create a self-enrollment training with an action
        self_enroll_training = OnlineTraining.objects.create(
            name="Self Enrollment Training",
            completion_time_limit=120,
            enabled=True,
            allow_self_enrollment=True,
        )

        # Create action that applies to all NEMO users
        action = OnlineTrainingAction.objects.create(
            online_training=self_enroll_training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 90},
            user_filter="all_nemo",
        )

        # Set initial access expiration for student
        initial_date = timezone.now()
        self.student_user.access_expiration = initial_date
        self.student_user.save()

        # Login as student user
        self.login_as(self.student_user)

        # Create training assignment (simulating self-enrollment)
        user_training = OnlineUserTraining.objects.create(
            prospective_user=self.prospective_student,
            online_training=self_enroll_training,
            start=timezone.now(),
        )

        # Verify training was created but not completed
        self.assertIsNone(user_training.end)
        self.assertFalse(user_training.completed())

        # Get the public training URL
        signed_id = TimestampSigner().sign(str(user_training.id))
        training_url = reverse("public_online_training_user_training", args=[signed_id])

        # Access the training page to verify it loads
        response = self.client.get(training_url)
        self.assertEqual(response.status_code, 200)

        # Complete the training via the public completion endpoint
        completion_url = reverse("public_online_training_complete_user_training")
        completion_data = {
            "completion_token": signed_id,
            "answer1": "test answer",
            "score": "95",
        }
        response = self.client.post(completion_url, completion_data)
        self.assertEqual(response.status_code, 200)

        # Verify training was completed
        user_training.refresh_from_db()
        self.assertIsNotNone(user_training.end)
        self.assertTrue(user_training.completed())
        self.assertEqual(user_training.completion_data["answer1"], "test answer")
        self.assertEqual(user_training.completion_data["score"], "95")

        # Verify action was triggered and access was extended
        self.student_user.refresh_from_db()
        expected_date = initial_date + timedelta(days=90)
        self.assertEqual(self.student_user.access_expiration, expected_date.date())

    def test_self_enrollment_training_without_matching_action(self):
        """Test that completing a training doesn't trigger actions that don't apply to the user."""
        from django.core.signing import TimestampSigner
        from django.urls import reverse

        from NEMO_online_training.models import OnlineUserTraining

        # Create a self-enrollment training
        self_enroll_training = OnlineTraining.objects.create(
            name="Self Enrollment Training 2",
            completion_time_limit=120,
            enabled=True,
            allow_self_enrollment=True,
        )

        # Create action that applies only to staff (not student)
        action = OnlineTrainingAction.objects.create(
            online_training=self_enroll_training,
            action_type=ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
            configuration={"extend_by_days": 90},
            user_filter=str(self.staff_type.id),  # Staff only
        )

        # Set initial access expiration for student
        initial_date = timezone.now()
        self.student_user.access_expiration = initial_date
        self.student_user.save()

        # Login as student user
        self.login_as(self.student_user)
        # Go to training page
        response = self.client.get(reverse("online_training_training", args=[self_enroll_training.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        user_training = OnlineUserTraining.objects.get(
            prospective_user=self.prospective_student, online_training=self_enroll_training
        )
        self.assertTrue(user_training)

        # Complete the training via the authenticated endpoint
        signed_id = TimestampSigner().sign(str(user_training.id))
        completion_url = reverse("public_online_training_complete_user_training")
        completion_data = {
            "completion_token": signed_id,
            "answer": "test",
        }
        response = self.client.post(completion_url, completion_data)
        self.assertEqual(response.status_code, 200)

        # Verify training was completed
        user_training.refresh_from_db()
        self.assertTrue(user_training.completed())

        # Verify action was NOT triggered (student's access should remain unchanged)
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.access_expiration, initial_date.date())
