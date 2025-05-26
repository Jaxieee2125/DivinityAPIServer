import os
import json
from pymongo import MongoClient, errors
from bson import ObjectId # Quan trọng để xử lý _id và các trường ObjectId khác
from datetime import datetime, timezone # Để xử lý các trường ngày tháng

# --- Cấu hình ---
MONGO_URI = "mongodb://localhost:27017/"  # Thay đổi nếu MongoDB của bạn ở địa chỉ khác
DATABASE_NAME = "MusicDatabase"        # Tên database bạn muốn import vào
DATA_DIR = "Database"                  # Thư mục chứa các file JSON

def get_collection_name_from_filename(filename):
    """Lấy tên collection từ tên file JSON (ví dụ: MusicDatabase.songs.json -> songs)."""
    parts = filename.split('.')
    if len(parts) > 2 and parts[-1].lower() == 'json':
        return parts[1]
    return None

def convert_ejson_to_bson(data):
    """
    Đệ quy chuyển đổi các giá trị EJSON ($oid, $date, $numberLong, etc.)
    thành các kiểu BSON tương ứng của Pymongo (ObjectId, datetime, int).
    """
    if isinstance(data, dict):
        # Xử lý các kiểu EJSON đặc biệt
        if len(data) == 1: # Các kiểu EJSON thường chỉ có 1 key
            if "$oid" in data:
                try:
                    # Đảm bảo giá trị của $oid là string và hợp lệ
                    if isinstance(data["$oid"], str) and ObjectId.is_valid(data["$oid"]):
                        return ObjectId(data["$oid"])
                except Exception:
                    # print(f"  WARNING: Could not convert to ObjectId: {data}. Keeping as dict.")
                    pass # Sẽ giữ lại dạng dict nếu không phải ObjectId hợp lệ
            elif "$date" in data:
                try:
                    date_val = data["$date"]
                    if isinstance(date_val, dict) and "$numberLong" in date_val: # Xử lý $date: { $numberLong: "timestamp_ms_str" }
                        timestamp_ms = int(date_val["$numberLong"])
                        return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
                    elif isinstance(date_val, (int, float)): # Milliseconds since epoch
                        return datetime.fromtimestamp(date_val / 1000.0, tz=timezone.utc)
                    elif isinstance(date_val, str): # Chuỗi ISO 8601
                        # Loại bỏ mili giây nếu có nhiều hơn 6 chữ số (Python không hỗ trợ quá 6)
                        if '.' in date_val and len(date_val.split('.')[1]) > 7 : # .xxxxxxxZ
                            date_val = date_val.split('.')[0] + '.' + date_val.split('.')[1][:6] + 'Z'
                        dt_obj = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                        return dt_obj if dt_obj.tzinfo else dt_obj.replace(tzinfo=timezone.utc)
                except Exception as e:
                    print(f"  WARNING: Could not parse EJSON date '{data['$date']}': {e}. Keeping as dict.")
                    pass
            elif "$numberLong" in data:
                try:
                    return int(data["$numberLong"])
                except ValueError:
                    pass
            # Thêm các kiểu EJSON khác nếu cần ($numberInt, $numberDouble, $regex, etc.)

        # Nếu không phải kiểu EJSON đặc biệt, đệ quy vào các giá trị của dict
        return {k: convert_ejson_to_bson(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_ejson_to_bson(item) for item in data]
    # Các kiểu cơ bản khác (string, int, float, bool, None) giữ nguyên
    return data

def import_data():
    try:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        print(f"Successfully connected to MongoDB: {MONGO_URI}, Database: {DATABASE_NAME}")
        # Kiểm tra kết nối
        client.admin.command('ping')
    except errors.ConnectionFailure as e:
        print(f"ERROR: Could not connect to MongoDB: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred during MongoDB connection: {e}")
        return

    if not os.path.isdir(DATA_DIR):
        print(f"ERROR: Data directory '{DATA_DIR}' not found at '{os.path.abspath(DATA_DIR)}'.")
        client.close()
        return

    print(f"Looking for JSON files in: {os.path.abspath(DATA_DIR)}")

    for filename in os.listdir(DATA_DIR):
        if filename.lower().endswith(".json"): # Chấp nhận cả .JSON
            collection_name = get_collection_name_from_filename(filename)
            if not collection_name:
                print(f"Could not determine collection name from '{filename}'. Skipping.")
                continue

            file_path = os.path.join(DATA_DIR, filename)
            print(f"\nImporting data from '{file_path}' into collection '{collection_name}'...")

            collection = db[collection_name]
            documents_to_insert = []

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Thử đọc như một mảng JSON lớn trước
                    try:
                        content_start = f.read(1) # Đọc ký tự đầu tiên
                        f.seek(0) # Quay lại đầu file
                        if content_start == '[':
                            data_array = json.load(f)
                            if isinstance(data_array, list):
                                documents_to_insert = data_array
                                print(f"  Detected JSON array format. Found {len(documents_to_insert)} documents.")
                            else: # Nếu là một object JSON duy nhất, bọc nó trong list
                                documents_to_insert = [data_array]
                                print(f"  Detected single JSON object. Processing 1 document.")
                        else: # Nếu không bắt đầu bằng '[', thử JSON Lines
                            raise json.JSONDecodeError("Not a JSON array", content_start, 0) # Gây lỗi để nhảy sang JSON Lines
                    except json.JSONDecodeError:
                        f.seek(0) # Quan trọng: Quay lại đầu file để đọc từng dòng
                        print("  File is not a single JSON array or object. Attempting to read as JSON Lines...")
                        for i, line in enumerate(f):
                            line = line.strip()
                            if line:
                                try:
                                    doc = json.loads(line)
                                    documents_to_insert.append(doc)
                                except json.JSONDecodeError as e_line:
                                    print(f"  WARNING: Could not parse line {i+1} in '{filename}': {e_line}. Skipping line.")
                        print(f"  Processed {len(documents_to_insert)} documents from JSON Lines format.")


                    if documents_to_insert:
                        # --- Chuyển đổi EJSON sang BSON ---
                        processed_documents = []
                        for doc_raw in documents_to_insert:
                            processed_doc = convert_ejson_to_bson(doc_raw)
                            processed_documents.append(processed_doc)
                        print(f"  Processed {len(processed_documents)} documents for BSON type conversion.")
                        # --------------------------------

                        # Tùy chọn: Xóa collection cũ trước khi import
                        # choice = input(f"  Drop collection '{collection_name}' before importing? (yes/NO): ").strip().lower()
                        # if choice == 'yes':
                        #     collection.drop()
                        #     print(f"  Dropped collection '{collection_name}'.")

                        try:
                            if processed_documents: # Chỉ insert nếu có document đã xử lý
                                result = collection.insert_many(processed_documents, ordered=False)
                                print(f"  Successfully inserted {len(result.inserted_ids)} documents into '{collection_name}'.")
                            else:
                                print("  No valid documents to insert after processing.")
                        except errors.BulkWriteError as bwe:
                            print(f"  WARNING: Bulk write error for '{collection_name}'. Some documents might not have been inserted due to duplicates or other issues.")
                            # In ra chi tiết các lỗi ghi
                            for error_detail in bwe.details.get('writeErrors', []):
                                print(f"    Index: {error_detail.get('index')}, Code: {error_detail.get('code')}, Message: {error_detail.get('errmsg')}")
                        except Exception as e_insert:
                            print(f"  ERROR inserting documents into '{collection_name}': {e_insert}")
                    else:
                        print(f"  No documents found or parsed in '{filename}'.")

            except FileNotFoundError:
                print(f"  ERROR: File '{file_path}' not found.")
            except Exception as e_file:
                print(f"  An unexpected error occurred with file '{filename}': {e_file}")

    client.close()
    print("\nMongoDB import process finished.")

if __name__ == '__main__':
    import_data()