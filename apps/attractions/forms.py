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
