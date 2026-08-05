# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                            |
| ----------------| ---------------------------------------------------|
| Họ và tên       | Nguyễn Việt Hải                                    |
| MSSV            | 2A202601656                                        |
| Khóa/Lớp        | K4                                                 |
| Vai trò chính   | Lead Multi-Agent Architect & Verification Engineer |
| Ngày hoàn thành | 2026-08-05                                         |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| **Multi-Agent Orchestrator & Trace Logging** | `src/coordinator.py`, `main.py` | Case input `input/EC_xxx.json` & Pandas DataFrames | Luồng Handoff 6 bước & Nhật ký `trace.jsonl` | Hoàn thành |
| **Policy Evaluation & LLM Reasoning** | `src/agents/policy_agent.py` | Dữ liệu đối soát từ 4 Agent chuyên biệt | Phân loại Lỗi, Lý do, Refund BRL, Action & Confidence động | Hoàn thành |
| **Verification & Quality Assurance** | `src/agents/verifier_agent.py` | Draft output dictionary & Customer request message | Verified Output JSON chuẩn hóa & Audited Confidence | Hoàn thành |
| **Multi-Model Metadata & Documentation** | `metadata.json`, `architecture.md` | Cấu hình mô hình $\le$ 10B & sơ đồ kiến trúc | Hồ sơ kiến trúc Multi-Agent & thông số hệ thống | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| :--- | :--- | :--- |
| **Data Loader & Order-Product Handoff** | `src/data_loader.py`, `src/agents/order_product_agent.py` | Khôi phục tên danh mục tiếng Bồ Đào Nha gốc từ CSV `product_category_name` |
| **Payment Reconciliation Ordering** | `src/agents/payment_agent.py` | Chuẩn hóa mảng `payment_types` giữ đúng thứ tự xuất hiện gốc trong CSV |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| :--- | :--- | :--- | :--- |
| **Xây dựng luồng điều phối 6 Agent** | `src/coordinator.py` | Luồng điều phối tuần tự 6 bước Handoff | Ghi nhật ký vết `trace.jsonl` (50 dòng) |
| **Triển khai quy tắc EC_POLICY_V2 & LLM Reasoning** | `src/agents/policy_agent.py` | Phân loại lỗi chính/phụ & Refund BRL | 50 file JSON tại `output/` |
| **Triển khai Verifier Agent & Audit Confidence** | `src/agents/verifier_agent.py` | Kiểm tra giới hạn mảng & Audit confidence | Chạy hàm `verify_and_clean()` |
| **Thiết lập Heterogeneous Dual-Model Architecture** | `metadata.json`, `architecture.md` | Cấu hình 2 mô hình Llama-3.1-8B-Instant (8B) & Qwen-2.5-7B-Instruct (7B) | File `metadata.json` & `architecture.md` |

### Bàn giao Output Cụ thể
- **50 File JSON Output (`output/EC_001.json` -> `EC_050.json`)**: Chứa kết quả điều tra khiếu nại của 50 đơn hàng với đầy đủ phân loại lỗi, bằng chứng `evidence_ids`, hành động xử lý và điểm tin cậy `confidence` biến thiên linh hoạt `[0.82 - 0.99]`.
- **File Nhật ký Vết `trace.jsonl`**: Ghi vết 6 bước Handoff giữa các Agent với chi tiết thông số thực tế của từng đơn hàng.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Xây dựng một hệ thống Multi-Agent vừa đảm bảo tính chính xác định lượng 100% (không vi phạm quy tắc Hard Gate 0 điểm) vừa thể hiện rõ tính minh bạch, lập luận chiều sâu qua mô hình ngôn ngữ lớn (LLM $\le$ 10B parameters).

### Cách triển khai
1. **Mô hình Hybrid (Deterministic Engine + LLM Reasoning)**:
   - Sử dụng Python Pandas Code cho các Agent dữ liệu (`CustomerAgent`, `OrderProductAgent`, `DeliveryAgent`, `PaymentAgent`) để tính toán thời gian `delivery_variance_hours`, tiền ship, và đối soát tài chính `reconciled` chính xác 100%.
   - Gọi mô hình **Groq `llama-3.1-8b-instant` (8B parameters)** trong `PolicyAgent` và `VerifierAgent` để đọc hiểu lời khiếu nại của khách hàng (`customer_request.message`), sinh điểm tin cậy `confidence` động và audit Schema trước khi xuất file.
2. **Quy trình Handoff 6 Bước**:
   - `Coordinator` $\rightarrow$ `CustomerAgent` $\rightarrow$ `OrderProductAgent` $\rightarrow$ `DeliveryAgent` $\rightarrow$ `PaymentAgent` $\rightarrow$ `PolicyAgent` $\rightarrow$ `VerifierAgent` $\rightarrow$ Export JSON & Trace Log.

### Input, output và contract

| Thành phần | Mô tả |
| :--- | :--- |
| **Input** | `input/EC_xxx.json` & 9 file Olist CSV datasets |
| **Output** | `output/EC_xxx.json` & `trace.jsonl` |
| **Module phụ thuộc** | `src/data_loader.py`, `src/config.py` |
| **Module sử dụng output** | System Auto-grader & Leaderboard Evaluator |
| **Điều kiện lỗi cần xử lý** | Đơn hàng không có item row, đơn bị canceled/unavailable, lỗi rate limit Groq API |

### Cách xác minh

```bash
python main.py
```

- **Kết quả mong đợi:** Xử lý thành công 50/50 cases, tạo mới `trace.jsonl` với 50 dòng log Handoff và 50 file JSON đạt điểm cao trên leaderboard.
- **Kết quả thực tế:** Tất cả 50 case hoàn tất thành công (`ALL 50 CASES PROCESSED SUCCESSFULLY`), điểm số đạt **79.0691 / 100**.
- **Artifact/log:** `trace.jsonl`, `output/EC_001.json` -> `output/EC_050.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn phương án triển khai logic phân loại khiếu nại và tính toán tiền refund cho 50 cases.
- **Các phương án đã cân nhắc:**
  1. *Phương án 1 (100% Prompt-based)*: Đẩy toàn bộ dữ liệu thô cho LLM qua Prompt để LLM tự chọn Primary Issue, tính tiền Refund và sinh JSON.
  2. *Phương án 2 (Hybrid Architecture - Lựa chọn)*: Dùng Deterministic Rule Engine quản lý quy tắc `EC_POLICY_V2` và tiền tệ, kết hợp Groq LLM (`llama-3.1-8b-instant`) cho Policy Reasoning và Confidence Auditing.
- **Phương án đã chọn:** Phương án 2 (Hybrid Architecture).
- **Lý do:** Đề bài có quy định nghiêm ngặt: *Case bị hard gate nhận 0 điểm*. Nếu phụ thuộc 100% vào Prompt, các model $\le$ 10B rất dễ tính sai 0.01 BRL hoặc chọn sai Cause Code $\rightarrow$ Dẫn đến bị 0 điểm cho case đó. Phương án 2 đảm bảo 0% nguy cơ Hard Gate mà vẫn khai thác tối đa năng lực lập luận ngôn ngữ tự nhiên của LLM.
- **Bằng chứng quyết định phù hợp:** Hệ thống vượt qua 100% các tiêu chí kiểm tra Schema, không bị bất kỳ lỗi Hard Gate nào và đạt mốc điểm 79.0691/100.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Điểm nộp bài ban đầu bị dừng ở mức cực thấp **5.0761 / 100 điểm**.
- **Lệnh hoặc bước tái hiện:** Nộp file nén `output.zip` ban đầu lên hệ thống chấm tự động.
- **Nguyên nhân gốc:** 
  1. File `src/data_loader.py` đã tự động dịch tên danh mục sản phẩm từ tiếng Bồ Đào Nha (`esporte_lazer`) sang tiếng Anh (`sports_leisure`), làm mất 15% trọng số Product Context.
  2. File `src/agents/policy_agent.py` thêm thừa hành động `verify_refund_completion` cho cả các đơn hoàn tiền freight refund.
  3. Thiếu Agent `OrderProductAgent` trong luồng ghi vết Handoff `trace.jsonl`.
- **Cách xử lý:** 
  1. Khôi phục tên danh mục `product_category_name` tiếng Bồ Đào Nha gốc từ CSV.
  2. Cập nhật logic `resolution_actions`: chỉ thêm `verify_refund_completion` khi `main_action == "issue_full_refund"`.
  3. Xây dựng mới `OrderProductAgent` và tích hợp vào luồng điều phối của `Coordinator`.
  4. Chuẩn hóa mảng `payment_types` giữ đúng thứ tự xuất hiện gốc trong CSV bằng `list(dict.fromkeys(...))`.
- **Cách xác minh sau khi sửa:** Chạy lại `python main.py` và nộp lại file Zip. Điểm số tăng vọt từ **5.0761 lên 79.0691 / 100 điểm (+74 điểm)**.
- **Bài học kỹ thuật:** Luôn tuân thủ tuyệt đối quy định về định dạng dữ liệu gốc (Raw Data Fidelity) và kiểm tra kỹ thứ tự các mảng trong Schema trước khi nộp bài.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ CSV Olist đến Multi-Agent Pipeline như thế nào?**  
   Dữ liệu 9 file CSV Olist trong `data/` được nạp vào memory (Pandas DataFrames) và tạo sẵn index theo `order_id`, `customer_id`, `product_id`, `seller_id` để các Agent truy vấn nhanh chóng.
2. **Evaluation set 50 cases dùng để đối soát ra sao?**  
   Bộ 50 file `input/EC_001.json` - `EC_050.json` cung cấp `claimed_order_id` và phạm vi điều tra. Hệ thống đối chiếu dữ liệu giao hàng, thanh toán và áp dụng bảng quy tắc `EC_POLICY_V2` để đưa ra kết luận chuẩn xác.
3. **Verifier Agent đóng vai trò gì trong pipeline?**  
   Verifier Agent kiểm tra chất lượng (Quality Check) độc lập trước khi xuất file: xác minh cấu trúc Schema, cắt giới hạn độ dài mảng (max 5 order, 5 item, 3 seller, 20 evidence...), kiểm tra format Evidence IDs và dải giá trị confidence `[0.82 - 0.99]`.
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

