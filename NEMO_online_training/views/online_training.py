import json
from datetime import timedelta
from logging import getLogger
from typing import Optional

from NEMO.decorators import user_office_or_manager_required
from NEMO.models import User, UserType
from NEMO.utilities import format_datetime, queryset_search_filter, render_email_template
from NEMO.views.pagination import SortedPaginator
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from NEMO_online_training.customization import OnlineTrainingCustomization
from NEMO_online_training.forms import TrainingRecordForm, TrainingUserForm
from NEMO_online_training.models import Training, TrainingRecord, TrainingUser

online_training_logger = getLogger(__name__)


@login_required
@require_GET
def user_online_trainings(request, training_user_id=None):
    user: User = request.user
    selected_status = request.GET.get("training_status", "incomplete")
    selected_user_type = request.GET.get("user_type", "")

    current_user_trainings = False
    single_user_view = False

    user_is_staff = user.is_user_office or user.is_facility_manager or user.is_superuser

    training_users = TrainingUser.objects_with_trainings()
    if not user_is_staff:
        current_user_trainings = True
        single_user_view = True
        training_users = training_users.filter(nemo_user=user)
    elif training_user_id:
        single_user_view = True
        training_users = training_users.filter(id=training_user_id)

    if selected_status == "complete":
        training_users = training_users.filter(all_trainings_completed=True)
    elif selected_status == "incomplete":
        training_users = training_users.filter(all_trainings_completed=False)
    if selected_user_type == "new":
        training_users = training_users.filter(nemo_user__isnull=True)
    elif selected_user_type == "nemo":
        training_users = training_users.filter(nemo_user__isnull=False)

    page = SortedPaginator(training_users, request, order_by="-last_updated").get_current_page()

    available_trainings = Training.objects.filter(enabled=True)
    for training_user in page:
        training_user.available_trainings = list()
        for online_training in available_trainings:
            if online_training.applies_to_user(training_user):
                training_user.available_trainings.append(online_training)

    # if bool(request.GET.get("csv", False)):
    #     return export_training_users(request, training_users.order_by("-last_updated"))

    dictionary = {
        "page": page,
        "current_user_trainings": current_user_trainings,
        "user_types": UserType.objects.all(),
        "user_is_staff": user_is_staff,
        "single_user_view": single_user_view,
        "selected_status": selected_status,
        "selected_user_type": selected_user_type,
    }
    return render(request, "NEMO_online_training/user_trainings/user_trainings.html", dictionary)


@require_GET
@user_office_or_manager_required
def search_training_users(request):
    return render(
        request,
        "NEMO_online_training/user_trainings/user_search.html",
        {"form": TrainingUserForm(), "user_types": UserType.objects.all()},
    )


@user_office_or_manager_required
@require_GET
def training_users_search_results(request):
    nemo_users: HttpResponse = queryset_search_filter(
        User.objects.all(), ["first_name", "last_name", "username", "email"], request
    )
    training_users: HttpResponse = queryset_search_filter(
        TrainingUser.objects.all(), ["_first_name", "_last_name", "_email"], request
    )
    return HttpResponse(
        json.dumps(json.loads(training_users.content) + json.loads(nemo_users.content)), "application/json"
    )


@user_office_or_manager_required
@require_GET
def create_training_user_from_nemo_user(request, nemo_user_id):
    nemo_user = get_object_or_404(User, pk=nemo_user_id)
    training_user = TrainingUser.create_from_nemo_user(nemo_user)
    return redirect("online_user_trainings", training_user_id=training_user.id)


@user_office_or_manager_required
@require_POST
def create_training_user(request):
    form = TrainingUserForm(request.POST or None)
    if form.is_valid():
        training_user = form.save()
        return redirect("online_user_trainings", training_user_id=training_user.id)
    return render(
        request,
        "NEMO_online_training/user_trainings/user_search.html",
        {"form": form, "user_types": UserType.objects.all()},
    )


@login_required
@require_GET
def create_nemo_user_from_new_user(request, training_user_id):
    training_user = get_object_or_404(TrainingUser, pk=training_user_id)
    nemo_new_user_url = reverse("create_or_modify_user", kwargs={"user_id": "new"})
    return redirect(
        f"{nemo_new_user_url}?first_name={training_user.first_name}&last_name={training_user.last_name}&email={training_user.email}&type={training_user.user_type_id or ''}&correlation_id={training_user_id}"
    )


@login_required
@require_GET
def training_without_assignment(request, online_training_id):
    online_training = get_object_or_404(Training, pk=online_training_id)
    if not online_training.allow_self_enrollment:
        return render(
            request,
            "NEMO_online_training/error_message.html",
            {
                "title": "Error",
                "message": "This training is not available for self enrollment, contact staff to be assigned this training",
            },
        )
    if not online_training.enabled:
        return render(
            request,
            "NEMO_online_training/error_message.html",
            {"title": "Error", "message": "This training is not available anymore"},
        )

    training_user = TrainingUser.create_from_nemo_user(request.user)
    online_user_training, created = TrainingRecord.objects.get_or_create(
        training_user=training_user, training=online_training, end=None
    )

    return redirect("online_training_user_training", user_training_id=online_user_training.id)


@require_GET
@login_required
def training(request, user_training_id):
    online_training_user = get_object_or_404(TrainingRecord, pk=user_training_id)
    if not online_training_user.training_user.nemo_user or request.user != online_training_user.training_user.nemo_user:
        return render(
            request,
            "NEMO_online_training/error_message.html",
            {"title": "Error", "message": "You do not have permission to complete this training"},
        )

    return redirect(online_training_user.generate_link())


@user_office_or_manager_required
@require_POST
def add_training_to_user(request, training_user_id, online_training_id):
    training_user = get_object_or_404(TrainingUser, pk=training_user_id)
    online_training = get_object_or_404(Training, pk=online_training_id)

    form = TrainingRecordForm(request.POST)
    form.instance.training_user = training_user
    form.instance.training = online_training

    if form.is_valid():
        online_training_user = form.save()
        online_training_user.generate_and_send_new_email()
        return JsonResponse({"success": True})
    else:
        # Return form errors in a format that JavaScript can handle
        errors = {}
        for field, error_list in form.errors.items():
            errors[field] = error_list
        return JsonResponse({"success": False, "errors": errors}, status=400)


@require_GET
@ensure_csrf_cookie
def public_user_training(request, signed_user_training_id):
    user_training_id = None

    try:
        signer = TimestampSigner()
        max_age = OnlineTrainingCustomization.get_int("online_training_link_validity_minutes") * 60

        # Just check validity
        user_training_id = signer.unsign(signed_user_training_id)
        online_training_user = get_object_or_404(TrainingRecord, id=user_training_id)
        if online_training_user.completed():
            return render(
                request,
                "NEMO_online_training/error_message.html",
                {"title": "Success", "message": _("This training has been completed!")},
            )

        # Now check the time limit
        user_training_id = signer.unsign(signed_user_training_id, max_age=max_age)

        # Extract the timestamp manually. Django token format is: value:timestamp:signature
        # We grab the middle part (timestamp) which is Base62 encoded.
        parts = signed_user_training_id.rsplit(":", 2)
        if len(parts) < 3:
            raise BadSignature()
    except (BadSignature, SignatureExpired) as e:
        if isinstance(e, SignatureExpired) and request.user and request.user.is_authenticated:
            return redirect("online_training_user", user_training_id=user_training_id)
        return render(
            request,
            "NEMO_online_training/public/invalid_training_link.html",
            {"user_training_id": user_training_id},
        )

    online_training_user.training_user.last_accessed = timezone.now()
    online_training_user.training_user.save(update_fields=["last_accessed"])
    error = check_training_validity(online_training_user)
    if error:
        return render(request, "NEMO_online_training/error_message.html", {"title": "Error", "message": error})
    else:
        completion_token = TimestampSigner().sign(user_training_id)
        online_training_user.start = timezone.now()
        online_training_user.save(update_fields=["start"])

        training_context = {
            "training_user": online_training_user.training_user,
            "training": online_training_user.training,
            "record": online_training_user,
        }

        online_training_rendered = render_email_template(
            online_training_user.training.html_content, training_context, request
        )
        return render(
            request,
            "NEMO_online_training/public/user_training.html",
            {
                "online_training_user": online_training_user,
                "online_training_rendered": online_training_rendered,
                "expires_at": online_training_user.start
                + timedelta(minutes=online_training_user.training.completion_time_limit),
                "completion_token": completion_token,
            },
        )


@require_POST
def public_generate_user_training_email(request, user_training_id):
    online_training_user = TrainingRecord.objects.filter(id=user_training_id).first()
    if not online_training_user:
        if request.POST.get("popup"):
            return HttpResponseBadRequest(_("Invalid link"))
        else:
            return render(
                request,
                "NEMO_online_training/error_message.html",
                {"title": "Error", "message": _("Invalid link")},
                status=400,
            )
    online_training_user.generate_and_send_new_email()
    return render(request, "NEMO_online_training/public/new_link_email_confirmation.html")


@require_POST
def public_complete_user_training(request):
    signed_user_training_id = request.POST.get("completion_token")
    user_training_id = None

    try:
        signer = TimestampSigner()
        # Just check validity
        user_training_id = signer.unsign(signed_user_training_id)
        # Now check the time limit
        online_training_user = get_object_or_404(TrainingRecord, pk=user_training_id)
        dynamic_limit_seconds = online_training_user.training.completion_time_limit * 60
        signer.unsign(signed_user_training_id, max_age=dynamic_limit_seconds)
    except (BadSignature, SignatureExpired):
        return render(
            request, "NEMO_online_training/public/invalid_training_link.html", {"user_training_id": user_training_id}
        )

    error = check_training_validity(online_training_user)
    if error:
        return render(request, "NEMO_online_training/error_message.html", {"title": "Error", "message": error})
    else:
        data = {}
        for key, values in request.POST.lists():
            # remove completion token and csrf token from the completion data
            if key in ["csrfmiddlewaretoken", "completion_token"]:
                continue
            if len(values) == 1:
                data[key] = values[0]
            else:
                data[key] = values
        online_training_user.complete(data)

    return HttpResponse()


def check_training_validity(online_user_training: TrainingRecord) -> Optional[Promise | str]:
    if not online_user_training.training.enabled:
        return _("This training is not available anymore!")
    if online_user_training.has_training_expired():
        return _(f"This training expired on {format_datetime(online_user_training.due_date)}")
    if online_user_training.end:
        return _("This training has been completed!")
    return None
