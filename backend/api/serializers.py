from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import Document


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'first_name', 'last_name')

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')


class DocumentSerializer(serializers.ModelSerializer):
    file_size = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ('id', 'original_filename', 'file', 'file_size', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_file_size(self, obj):
        if obj.file:
            return obj.file.size
        return 0

    def validate_file(self, value):
        if value.size > 10 * 1024 * 1024:  # 10MB limit
            raise serializers.ValidationError("File size cannot exceed 10MB")

        allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only PDF, PPT, and DOCX files are allowed")

        return value


class AskQuestionSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()
    question = serializers.CharField(max_length=1000)

    def validate_document_id(self, value):
        user = self.context['request'].user
        try:
            document = Document.objects.get(id=value, user=user)
        except Document.DoesNotExist:
            raise serializers.ValidationError("Document not found or access denied")
        return value