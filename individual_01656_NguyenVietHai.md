# Member Role Report — Day 9: Multi Agent A2A

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình. Không sao chép nguyên báo cáo chung hoặc báo cáo của thành viên khác. Thay nội dung trong dấu `[ ]` và xóa các dòng hướng dẫn không cần thiết trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin       | Nội dung        |
| -----------------| -----------------|
| Họ và tên       | Nguyễn Việt Hải |
| MSSV            | 2A202601656     |
| Khóa/Lớp        | [K4]            |
| Vai trò chính   | [Vai trò]       |
| Ngày hoàn thành | [YYYY-MM-DD]    |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao   | Trạng thái                            |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| [Phần việc]        | [File/hàm]         | [Input]        | [Output/artifact] | [Hoàn thành/Một phần/Chưa hoàn thành] |
| [Phần việc]        | [File/hàm]         | [Input]        | [Output/artifact] | [Hoàn thành/Một phần/Chưa hoàn thành] |

Chỉ nhận ownership cho phần bạn trực tiếp thực hiện. Liên hệ rõ phần việc của bạn với đầu vào, đầu ra và các thành viên phụ thuộc vào phần đó.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| [Debug/tích hợp/tài liệu] | [Tên hoặc module]             | [Kết quả và bằng chứng] |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| [Mô tả cụ thể]        | [Đường dẫn file]            | [Artifact/metrics/report] | [Lệnh/artifact] |
| [Mô tả cụ thể]        | [Đường dẫn file]            | [Artifact/metrics/report] | [Lệnh/artifact] |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

[Mô tả artifact, metric, report hoặc kết quả tích hợp.]

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

[Phần của bạn giải quyết vấn đề gì trong pipeline?]

### Cách triển khai

[Mô tả thuật toán, quy tắc dữ liệu, orchestration hoặc quyết định chính. Không chỉ chép lại tên hàm.]

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | [Schema, artifact hoặc tham số]        |
| Output                  | [Schema, artifact hoặc giá trị trả về] |
| Module phụ thuộc        | [Module/file liên quan]                |
| Module sử dụng output   | [Module/file liên quan]                |
| Điều kiện lỗi cần xử lý | [Trường hợp thực tế]                   |

### Cách xác minh

```bash
[Ghi lệnh thực tế đã chạy]
```

- **Kết quả mong đợi:** [Mô tả.]
- **Kết quả thực tế:** [Mô tả.]
- **Artifact/log:** [Đường dẫn; không chứa secret.]

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** [Vấn đề hoặc lựa chọn cần quyết định.]
- **Các phương án đã cân nhắc:** [Ít nhất hai phương án.]
- **Phương án đã chọn:** [Lựa chọn.]
- **Lý do:** [Trade-off về correctness, data quality, reproducibility, cost hoặc độ phức tạp.]
- **Bằng chứng quyết định phù hợp:** [Metric, artifact hoặc kết quả thử nghiệm.]

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** [Che toàn bộ secret trước khi ghi.]
- **Lệnh hoặc bước tái hiện:** [Lệnh/bước.]
- **Nguyên nhân gốc:** [Root cause, không chỉ mô tả triệu chứng.]
- **Cách xử lý:** [Thay đổi cụ thể.]
- **Cách xác minh sau khi sửa:** [Lệnh và kết quả.]
- **Điều học được:** [Bài học kỹ thuật.]

Nếu chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** [Module/artifact.]
- **Những gì đã loại trừ:** [Các giả thuyết đã kiểm tra.]
- **Bước tiếp theo:** [Hành động có thể kiểm chứng.]

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn:

1. **Dữ liệu đi từ CSV Olist đến Multi-Agent Pipeline như thế nào?**
   Dữ liệu 9 file CSV Olist trong `data/` được nạp vào memory (Pandas DataFrames) và tạo sẵn index theo `order_id`, `customer_id`, `product_id`, `seller_id` để các Agent truy vấn nhanh chóng.
2. **Evaluation set 50 cases dùng để đối soát ra sao?**
   Bộ 50 file `input/EC_001.json` - `EC_050.json` cung cấp `claimed_order_id` và phạm vi điều tra. Hệ thống đối chiếu dữ liệu giao hàng, thanh toán và áp dụng bảng quy tắc `EC_POLICY_V2` để đưa ra kết luận chuẩn xác.
3. **Verifier Agent đóng vai trò gì trong pipeline?**
   Verifier Agent kiểm tra chất lượng (Quality Check) độc lập trước khi xuất file: xác minh cấu trúc Schema, cắt giới hạn độ dài mảng (max 5 order, 5 item, 3 seller, 20 evidence...), kiểm tra format Evidence IDs và dải giá trị confidence `[0, 1]`.
4. **Vì sao phải ghi vết trace.jsonl?**
   File `trace.jsonl` ghi lại toàn bộ sự kiện handoff thực tế giữa các Agent trong hệ thống, đảm bảo tính minh bạch, tái hiện được luồng điều tra (reproducibility) và chứng minh hệ thống thực sự sử dụng Multi-Agent.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Việt Hải  
**Ngày xác nhận:** 2026-08-05  

