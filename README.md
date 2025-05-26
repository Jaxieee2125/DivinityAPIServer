# Divinity API Server

Đây là backend API cho ứng dụng nghe nhạc Divinity, được xây dựng bằng Python, Django, và Django REST Framework, với MongoDB làm cơ sở dữ liệu chính. API này cung cấp các endpoints để quản lý người dùng, bài hát, nghệ sĩ, albums, playlists, thể loại nhạc, và các yêu cầu bài hát.

## Các Tính năng Chính (Backend)

*   **Xác thực & Phân quyền:**
    *   Sử dụng JWT (JSON Web Tokens) với `djangorestframework-simplejwt` cho việc xác thực.
    *   View login tùy chỉnh (`AdminLoginView`) để xác thực admin dựa trên collection `admin` trong MongoDB.
    *   Custom permission class (`IsAdminFromMongo`) để bảo vệ các API endpoint yêu cầu quyền admin, dựa trên việc kiểm tra sự tồn tại của user trong collection `admin`.
    *   Các API public (ví dụ: lấy danh sách bài hát) và API yêu cầu đăng nhập người dùng thông thường được phân quyền tương ứng.
*   **Quản lý CRUD cho các thực thể chính:**
    *   **Songs:** Thêm, sửa, xóa, lấy danh sách, lấy chi tiết. Bao gồm xử lý upload file nhạc và tự động đổi tên file theo `_id`.
    *   **Artists:** Thêm, sửa, xóa, lấy danh sách, lấy chi tiết. Bao gồm xử lý upload ảnh đại diện (avatar).
    *   **Albums:** Thêm, sửa, xóa, lấy danh sách, lấy chi tiết. Bao gồm xử lý upload ảnh bìa và liên kết với nghệ sĩ.
    *   **Users (Quản lý bởi Admin):** Admin có thể xem, thêm, sửa (bao gồm reset password), xóa người dùng. Mật khẩu được hash an toàn.
    *   **MusicGenres:** Thêm, sửa, xóa, lấy danh sách.
    *   **Playlists:**
        *   Người dùng đã đăng nhập có thể tạo playlist mới.
        *   Lấy danh sách playlist (public và của user).
        *   Lấy chi tiết playlist (bao gồm danh sách các bài hát chi tiết).
        *   Sửa thông tin playlist (tên, mô tả, is_public).
        *   Thêm/Xóa bài hát khỏi playlist.
        *   Xóa playlist (chỉ chủ sở hữu hoặc admin).
*   **API Options cho Frontend Selects:** Cung cấp các endpoint rút gọn (`/artists/options/`, `/albums/options/`, `/musicgenres/options/`) để frontend dễ dàng lấy dữ liệu cho các thẻ `<select>`.
*   **Xử lý File Media:**
    *   Phục vụ file media (ảnh, nhạc) với URL tuyệt đối.
    *   Hỗ trợ HTTP Range Requests cho việc tua (seeking) file audio hiệu quả.
*   **Tìm kiếm Tổng hợp:** Endpoint `/api/search/` để tìm kiếm bài hát, album, nghệ sĩ.
*   **Quản lý Yêu cầu Bài hát (Song Requests):**
    *   API cho người dùng gửi yêu cầu bài hát mới.
    *   API cho admin xem và cập nhật trạng thái (pending, approved, rejected, added) của các yêu cầu.

## Công nghệ Sử dụng

*   **Python 3.x**
*   **Django 4.x**
*   **Django REST Framework (DRF)**
*   **MongoDB:** Cơ sở dữ liệu chính, tương tác qua `pymongo`.
*   **`djangorestframework-simplejwt`:** Cho xác thực bằng JWT.
*   **`django-cors-headers`:** Xử lý Cross-Origin Resource Sharing.
*   **`Pillow`:** Thư viện xử lý ảnh (cần cho `ImageField` của DRF nếu dùng).

## Thiết lập Môi trường Development

1.  **Clone Repository:**
    ```bash
    git clone https://github.com/Jaxieee2125/DivinityAPIServer.git
    cd DivinityAPIServer
    ```

2.  **Tạo và Kích hoạt Môi trường ảo:**
    ```bash
    python -m venv venv
    # Windows:
    venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```

3.  **Cài đặt Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Cấu hình MongoDB:**
    *   Đảm bảo MongoDB server đang chạy.
    *   Tạo database với tên bạn đã đặt trong `db = client['MusicDatabase']` ở MusicAPI/views.py.
    *   Có thể import database mẫu bằng script import_database.py trong thư mục gốc
         ```bash
         python import_database.py
         ```
         
      * Tài khoản Admin :
         - Username: admin
         - Password: 123456789
      * Tài khoản User :
         - Username: user
         - Password: abc@1234


5.  **Tạo Tài khoản Admin (Nếu chưa có):**
    *   Chạy script Python tùy chỉnh (ví dụ: `create_admin.py` bạn đã tạo) để thêm một bản ghi admin vào collection `users` và `admin` trong MongoDB với mật khẩu đã được hash.
        ```bash
        python create_admin.py
        ```

6.  **Chạy Development Server:**
    ```bash
    python manage.py runserver
    ```
    API server sẽ chạy trên `http://127.0.0.1:8000/`.

## Cấu trúc API Endpoints Chính (Ví dụ)

*   `/api/token/`: **POST** - Lấy Access và Refresh Token (Login Admin).
*   `/api/token/refresh/`: **POST** - Làm mới Access Token.
*   `/api/songs/`: **GET** (list), **POST** (create song - admin).
*   `/api/songs/<id>/`: **GET** (detail), **PUT** (update - admin), **DELETE** (delete - admin).
*   `/api/artists/`: **GET** (list), **POST** (create - admin).
*   `/api/artists/<id>/`: **GET** (detail), **PUT** (update - admin), **DELETE** (delete - admin).
*   `/api/artists/<id>/albums/`: **GET** - Lấy album của nghệ sĩ.
*   `/api/artists/<id>/top-tracks/`: **GET** - Lấy top tracks của nghệ sĩ.
*   `/api/albums/`: **GET** (list), **POST** (create - admin).
*   `/api/albums/<id>/`: **GET** (detail), **PUT** (update - admin), **DELETE** (delete - admin).
*   `/api/albums/<id>/songs/`: **GET** - Lấy bài hát của album.
*   `/api/musicgenres/`: **GET** (list), **POST** (create - admin).
*   `/api/musicgenres/<id>/`: **GET** (detail), **PUT** (update - admin), **DELETE** (delete - admin).
*   `/api/playlists/`: **GET** (list - public & user's), **POST** (create - authenticated user).
*   `/api/playlists/<id>/`: **GET** (detail - public/owner/admin), **PUT** (update - owner/admin), **DELETE** (delete - owner/admin).
*   `/api/user/favourites/toggle/<song_id>/`: **POST** - Thêm/Xóa bài hát yêu thích (authenticated user).
*   `/api/user/favourites/status/?song_ids=...`: **GET** - Kiểm tra trạng thái yêu thích (authenticated user).
*   `/api/user/liked-songs/`: **GET** - Lấy danh sách bài hát yêu thích của user (authenticated user).
*   `/api/user/song-requests/`: **GET**, **POST** (authenticated user).
*   `/api/admin/users/`: **GET**, **POST** (admin).
*   `/api/admin/users/<id>/`: **GET**, **PUT**, **DELETE** (admin).
*   `/api/admin/song-requests/`: **GET** (admin).
*   `/api/admin/song-requests/<id>/`: **PUT** (update status - admin).
*   `/api/admin/stats/`: **GET** (admin).
*   `/api/artists/options/`, `/api/albums/options/`, `/api/musicgenres/options/`: **GET** (admin - cho form selects).


## Các bước tiếp theo cho Backend

*   Hoàn thiện logic phân quyền chi tiết cho từng API.
*   Tối ưu hóa các truy vấn MongoDB, đặc biệt là các aggregation pipeline với `$lookup`.
*   Thêm validation dữ liệu mạnh mẽ hơn trong serializers.
*   Viết Unit Test và Integration Test.
*   Chuẩn bị cho việc triển khai (Deployment).

## Đóng góp

Nếu bạn muốn đóng góp cho dự án, vui lòng tạo một Issue để thảo luận về thay đổi bạn muốn thực hiện hoặc một Pull Request với các cải tiến của bạn.

## Tác giả

*   **Jaxieee2125** - _Phát triển chính_ - [Jaxieee2125](https://github.com/Jaxieee2125)
*   **thinhziro239** - [thinhziro239](https://github.com/thinhziro239)
*   **doanphuc394** - [doanphuc394](https://github.com/doanphuc394)

## Giấy phép

Dự án này được cấp phép dưới Giấy phép MIT - xem file `LICENSE.md` (nếu có) để biết chi tiết.
