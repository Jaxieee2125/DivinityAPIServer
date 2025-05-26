import os
import sys
from getpass import getpass # Để nhập mật khẩu một cách an toàn hơn

# Thêm đường dẫn dự án Django vào sys.path để có thể import settings
# Điều chỉnh đường dẫn này nếu script không nằm ở thư mục gốc dự án
project_path = os.path.dirname(os.path.abspath(__file__)) # Lấy thư mục hiện tại của script
sys.path.append(project_path)

# Thiết lập môi trường Django (cần thiết để dùng settings và hashers)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MusicServer.settings') # <<< THAY 'MusicServer' bằng tên thư mục project settings của bạn
import django
django.setup()

from django.conf import settings
from django.contrib.auth.hashers import make_password
from pymongo import MongoClient, errors
from bson import ObjectId # Import ObjectId

def create_mongo_admin():
    print("--- Create MongoDB Admin User for Divinity ---")

    # --- Lấy thông tin kết nối MongoDB từ settings.py (nếu có) ---
    try:
        mongo_url = getattr(settings, 'MONGO_DB_URL', 'mongodb://localhost:27017/') # <<< THAY 'mongodb://localhost:27017/' bằng đường dẫn đến server của bạn
        db_name = getattr(settings, 'MONGO_DB_NAME', 'MusicDatabase') # <<< THAY 'MusicDatabase' bằng tên DB của bạn
        client = MongoClient(mongo_url)
        db = client[db_name]
        # Kiểm tra kết nối
        client.admin.command('ping')
        print(f"Successfully connected to MongoDB: {db_name}")
    except errors.ConnectionFailure as e:
        print(f"ERROR: Could not connect to MongoDB: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred during MongoDB connection: {e}")
        return
    # ---------------------------------------------------------

    # --- Thu thập thông tin Admin ---
    username = input("Enter admin username: ").strip()
    email = input("Enter admin email: ").strip()

    while True:
        password = getpass("Enter admin password: ") # Nhập mật khẩu ẩn
        password_confirm = getpass("Confirm admin password: ")
        if password == password_confirm:
            if not password: # Kiểm tra mật khẩu rỗng
                 print("Password cannot be empty. Please try again.")
            else:
                break
        else:
            print("Passwords do not match. Please try again.")

    # --- Kiểm tra thông tin cơ bản ---
    if not username:
        print("Username cannot be empty.")
        return
    if not email: # Có thể thêm validation email phức tạp hơn
        print("Email cannot be empty.")
        return

    # --- Kiểm tra xem username hoặc email đã tồn tại trong collection 'users' chưa ---
    if db.users.count_documents({'username': username}, limit = 1) > 0:
        print(f"Error: Username '{username}' already exists in the 'users' collection.")
        client.close()
        return
    if db.users.count_documents({'email': email}, limit = 1) > 0:
        print(f"Error: Email '{email}' already exists in the 'users' collection.")
        client.close()
        return
    # Kiểm tra trong collection 'admin' (nếu username là duy nhất ở đó)
    if db.admin.count_documents({'username': username}, limit = 1) > 0:
        print(f"Error: Username '{username}' already exists in the 'admin' collection.")
        client.close()
        return
    # -------------------------------------------------------------------------------


    # --- Tạo document cho collection 'users' (nếu cần) ---
    # Giả sử admin cũng là một user trong hệ thống
    user_doc = {
        'username': username,
        'email': email,
        'password': make_password(password), # Hash mật khẩu
        'is_staff': True, # Đánh dấu đây là staff/admin trong collection users
        'is_active': True,
        'date_joined': datetime.utcnow(), # Ngày tham gia
        # Thêm các trường mặc định khác cho user nếu có
        'favourite_songs': [],
        'profile_picture': None,
        'date_of_birth': None,
    }
    try:
        user_insert_result = db.users.insert_one(user_doc)
        user_mongo_id = user_insert_result.inserted_id
        print(f"Successfully created base user record with ID: {user_mongo_id}")
    except errors.PyMongoError as e:
        print(f"Error creating base user record in 'users' collection: {e}")
        client.close()
        return
    # -----------------------------------------------------

    # --- Tạo document cho collection 'admin' ---
    admin_doc = {
        'user_id': user_mongo_id, # Tham chiếu đến _id của user trong collection 'users'
        'username': username,     # Có thể giữ lại username để query dễ hơn
        'password': make_password(password), # Hash lại mật khẩu (hoặc dùng chung hash từ user_doc)
                                            # Thường thì nên hash riêng cho admin collection
                                            # nếu mật khẩu admin có thể khác user thường.
                                            # Nếu admin login bằng chính user record (is_staff=True)
                                            # thì không cần trường password ở đây.
        # Thêm các trường đặc thù cho admin nếu có (ví dụ: roles, permissions cấp cao)
        'created_at': datetime.utcnow(),
    }
    try:
        db.admin.insert_one(admin_doc)
        print(f"Successfully created admin record for user ID: {user_mongo_id}")
        print(f"Admin '{username}' created successfully!")
    except errors.PyMongoError as e:
        print(f"Error creating admin record in 'admin' collection: {e}")
        # Cân nhắc rollback việc tạo user_doc nếu tạo admin thất bại
        db.users.delete_one({'_id': user_mongo_id})
        print(f"Rolled back: Deleted base user record {user_mongo_id}")
    finally:
        client.close()
        print("MongoDB connection closed.")

if __name__ == '__main__':
    from datetime import datetime, timezone # Import datetime ở đây để dùng trong main
    create_mongo_admin()