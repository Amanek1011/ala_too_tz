from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Review
from .translations import text

User = get_user_model()


class StyledFieldsMixin:
    input_class = "input-field"

    def apply_common_styles(self):
        for field_name, field in self.fields.items():
            widget = field.widget
            widget.attrs.setdefault("class", self.input_class)
            widget.attrs.setdefault("autocomplete", field_name)


class SignInForm(StyledFieldsMixin, AuthenticationForm):
    def __init__(self, *args, lang="ru", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = text(lang, "username")
        self.fields["password"].label = text(lang, "password")
        self.fields["username"].widget.attrs.update(
            {
                "class": self.input_class,
                "placeholder": text(lang, "username"),
                "autocomplete": "username",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": self.input_class,
                "placeholder": text(lang, "password"),
                "autocomplete": "current-password",
            }
        )


class SignUpForm(StyledFieldsMixin, UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, lang="ru", **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "username": text(lang, "username"),
            "email": text(lang, "email"),
            "password1": text(lang, "password"),
            "password2": text(lang, "confirm_password"),
        }
        placeholders = {
            "username": text(lang, "username"),
            "email": text(lang, "email"),
            "password1": text(lang, "password"),
            "password2": text(lang, "confirm_password"),
        }
        autocompletes = {
            "username": "username",
            "email": "email",
            "password1": "new-password",
            "password2": "new-password",
        }

        for field_name, field in self.fields.items():
            field.label = labels[field_name]
            field.widget.attrs.update(
                {
                    "class": self.input_class,
                    "placeholder": placeholders[field_name],
                    "autocomplete": autocompletes[field_name],
                }
            )


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(i, str(i)) for i in range(1, 6)],
        coerce=int,
        empty_value=None,
        widget=forms.RadioSelect(attrs={"class": "rating-radio"}),
    )

    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {
            "comment": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": "textarea-field review-textarea",
                }
            ),
        }

    def __init__(self, *args, lang="ru", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].label = text(lang, "your_rating")
        self.fields["comment"].label = text(lang, "comment")
        self.fields["comment"].widget.attrs["placeholder"] = text(lang, "review_placeholder")


class RouteRequestForm(forms.Form):
    age = forms.IntegerField(min_value=7, max_value=100)
    interests = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple)
    duration_hours = forms.IntegerField(min_value=2, max_value=12)
    physical_activity = forms.ChoiceField()
    accessibility_required = forms.BooleanField(required=False)
    with_children = forms.BooleanField(required=False)

    def __init__(self, *args, lang="ru", **kwargs):
        super().__init__(*args, **kwargs)

        interest_choices = [
            ("history", text(lang, "route_interest_history")),
            ("nature", text(lang, "route_interest_nature")),
            ("culture", text(lang, "route_interest_culture")),
            ("adventure", text(lang, "route_interest_adventure")),
            ("wellness", text(lang, "route_interest_wellness")),
            ("city", text(lang, "route_interest_city")),
        ]
        activity_choices = [
            ("low", text(lang, "route_activity_low")),
            ("medium", text(lang, "route_activity_medium")),
            ("high", text(lang, "route_activity_high")),
        ]

        self.fields["age"].label = text(lang, "route_age_label")
        self.fields["age"].widget = forms.NumberInput(
            attrs={
                "class": "input-field",
                "min": 7,
                "max": 100,
                "placeholder": "28",
            }
        )

        self.fields["interests"].label = text(lang, "route_interests_label")
        self.fields["interests"].choices = interest_choices
        self.fields["interests"].widget.attrs.update({"class": "interest-checkboxes"})

        self.fields["duration_hours"].label = text(lang, "route_duration_label")
        self.fields["duration_hours"].widget = forms.NumberInput(
            attrs={
                "class": "input-field",
                "min": 2,
                "max": 12,
                "step": 1,
            }
        )
        self.fields["duration_hours"].initial = 6

        self.fields["physical_activity"].label = text(lang, "route_activity_label")
        self.fields["physical_activity"].choices = activity_choices
        self.fields["physical_activity"].widget = forms.Select(attrs={"class": "input-field"})
        self.fields["physical_activity"].initial = "medium"

        self.fields["accessibility_required"].label = text(lang, "route_accessibility_label")
        self.fields["accessibility_required"].widget = forms.CheckboxInput(attrs={"class": "switch-input"})

        self.fields["with_children"].label = text(lang, "route_family_label")
        self.fields["with_children"].widget = forms.CheckboxInput(attrs={"class": "switch-input"})

    def clean_interests(self):
        interests = self.cleaned_data["interests"]
        if not interests:
            raise forms.ValidationError("Please choose at least one interest.")
        return interests
