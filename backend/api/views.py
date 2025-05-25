import os
import io
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import google.generativeai as genai
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import Document
from .serializers import (
    UserRegistrationSerializer,
    UserSerializer,
    DocumentSerializer,
    AskQuestionSerializer
)

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def homepage(request):
    return Response({
        'message': 'Welcome to Document Portal API',
        'version': '1.0',
        'endpoints': {
            'register': '/api/register/',
            'login': '/api/login/',
            'logout': '/api/logout/',
            'profile': '/api/profile/',
            'documents': '/api/documents/',
            'ask_question': '/api/ask/',
        }
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if username and password:
        user = authenticate(username=username, password=password)
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })

    return Response(
        {'error': 'Invalid credentials'},
        status=status.HTTP_401_UNAUTHORIZED
    )


@api_view(['POST'])
def logout(request):
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        return Response({'message': 'Logout successful'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


def extract_text_from_file(file_path, file_type):
    try:
        if file_type == 'application/pdf':
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            if not text.strip():
                doc = fitz.open(file_path)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    text += pytesseract.image_to_string(img)
                doc.close()
            return text

        elif file_type in ['image/jpeg', 'image/png', 'image/tiff']:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
            return text

    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""
    return ""


@method_decorator(csrf_exempt, name='dispatch')
class DocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser]  # This handles file uploads
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Document.objects.all()

    def post(self, request, *args, **kwargs):
        print("=== UPLOAD DEBUG INFO ===")
        print(f"Content-Type: {request.content_type}")
        print(f"FILES: {list(request.FILES.keys())}")
        print(f"POST data: {dict(request.POST)}")

        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['file']

        # Create test user if needed
        try:
            test_user = User.objects.first()
            if not test_user:
                test_user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        except:
            test_user = User.objects.create_user('testuser', 'test@example.com', 'testpass')

        # Create document
        try:
            document = Document.objects.create(
                user=test_user,
                file=file,
                original_filename=file.name
            )

            # Extract text
            try:
                file_path = document.file.path
                file_type = file.content_type
                extracted_text = extract_text_from_file(file_path, file_type)
                document.extracted_text = extracted_text
                document.save()
                print(f"Text extracted successfully: {len(extracted_text)} characters")
            except Exception as e:
                print(f"Text extraction failed: {e}")

            # Return response
            serializer = DocumentSerializer(document)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error creating document: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing

    def get_queryset(self):
        return Document.objects.all()


@api_view(['POST'])
@permission_classes([permissions.AllowAny])  # Changed for testing
def ask_question(request):
    document_id = request.data.get('document_id')
    question = request.data.get('question')

    if not document_id or not question:
        return Response({'error': 'Document ID and question are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        document = Document.objects.get(id=document_id)

        if not document.extracted_text:
            return Response(
                {'error': 'No text content found in this document'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if settings.GEMINI_API_KEY:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"""
                Hey there, smart assistant here! 🚀 I’ve just received a new question, and I need to analyze the following document content to give the BEST possible answer.

                📄 Here’s what the document says (showing you the first part because it’s long):
                ---
                {document.extracted_text[:4000]}
                ---

                🤔 Now, here’s the question I’ve been asked to answer:
                **"{question}"**

                🎯 My goal? To provide a **clear, accurate, and super helpful** answer using ONLY the information found in the document above. I won’t make up stuff — if it’s not in the document, I’ll let you know.

                So here it goes… Let's break it down and give a smart, to-the-point answer that even your grandma would understand (if she were into this stuff). Ready? Let’s go!
                """

                response = model.generate_content(prompt)
                answer = response.text
            except Exception as e:
                answer = f"AI service temporarily unavailable. Error: {str(e)}"
        else:
            answer = "AI service is not configured. Please contact the administrator."

        return Response({
            'question': question,
            'answer': answer,
            'document': document.original_filename
        })

    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_profile(request):
    return Response(UserSerializer(request.user).data)