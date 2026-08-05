# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                            |
| --------------- | -------------------------------------------------------------------- |
| Họ và tên       | Nguyễn Thái Tú                                                      |
| MSSV            | 2A202601504                                                          |
| Khóa/Lớp        | K4                                                                    |
| Vai trò chính   | Xây dựng và vận hành pipeline multi-agent trên nhánh cá nhân `thaitu`: coordinator, 6 agent, đóng gói và debug bài nộp |
| Ngày hoàn thành | 2026-08-05                                                            |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Toàn bộ pipeline multi-agent (khởi tạo) | `main.py`, `src/coordinator.py`, `src/agents/*.py`, `src/data_layer.py`, `src/schema.py`, `src/llm_client.py`, `src/utils.py` | 50 file `input/EC_0xx.json` + 9 CSV Olist trong `data/` | 50 file `output/EC_0xx.json`, `trace.jsonl`, `metadata.json` | Hoàn thành |
| Fix bug `category_names` bị dịch sai ngôn ngữ | `src/agents/order_product_agent.py`, `src/data_layer.py` | Output sai (dịch sang tiếng Anh qua `product_category_name_translation.csv`) | Output đúng (giữ nguyên `product_category_name` gốc tiếng Bồ Đào Nha) | Hoàn thành |
| Thử nghiệm và đánh giá công thức `confidence` | `src/agents/policy_agent.py` (`_confidence`) | Baseline điểm 67.9861 | Kết luận: đổi công thức không cải thiện điểm (67.9347) → revert về bản cũ | Hoàn thành |
| Kiểm chứng output trước khi nộp | `src/agents/verifier_agent.py`, script kiểm tra rời | 50 file `output/EC_0xx.json` + CSV thật | Xác nhận 0/50 case có evidence ID sai, cap vượt giới hạn, hoặc null-handling sai | Hoàn thành |
| Đóng gói và khắc phục sự cố nộp bài | `output/` → zip | 50 file JSON | `output.zip` đúng cấu trúc `output/EC_0xx.json`, đặt tại thư mục nộp bài riêng | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Không có hoạt động hỗ trợ chéo thành viên khác được ghi nhận trong phạm vi báo cáo này | — | Toàn bộ công việc thực hiện độc lập trên nhánh `thaitu` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Phát hiện và fix bug `category_names` dịch sai ngôn ngữ | `src/agents/order_product_agent.py` | Điểm bài nộp tăng từ 0đ lên 67.9861đ | So khớp `output/EC_001.json` với file tham chiếu `ok.txt`, chạy lại `py main.py` cho cả 50 case |
| Chạy `verifier_agent.verify()` thật trên toàn bộ output | `src/agents/verifier_agent.py` | 50/50 file không có lỗi evidence ID, cap, null-handling | `py -c "..."` gọi `verify()` trực tiếp với `OlistData('data')`, in kết quả `files with issues: 0` |
| Khôi phục repo sau khi một commit local vô tình tái tạo lại bug đã fix | Git (`git log`, `git reset --hard`) | Repo local khớp lại `origin/thaitu`, output đúng bản đã fix | `git log --oneline`, `git status`, `git diff HEAD` xác nhận sạch |

Output cụ thể phần việc của tôi tạo ra:

`output/EC_001.json` (và 49 case còn lại) sau khi sửa: `category_names` giữ đúng giá trị gốc `"beleza_saude"` (tiếng Bồ Đào Nha, đúng cột `product_category_name` trong `products.csv`) thay vì bị dịch sang `"health_beauty"`. Đây là thay đổi trực tiếp khiến điểm bài nộp đi từ 0đ lên 67.9861đ.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Bài nộp ban đầu (file zip `output/`) bị hệ thống chấm điểm trả về 0đ dù nội dung JSON có vẻ hợp lệ về mặt cấu trúc (đúng key, đúng schema, evidence ID resolve được vào CSV thật, cap không vượt giới hạn). Cần tìm ra sai lệch thực sự giữa output pipeline sinh ra và kết quả "chuẩn" mà hệ thống mong đợi, sau đó sửa và xác nhận lại bằng điểm số thật.

### Cách triển khai

So sánh trực tiếp `output/EC_001.json` do pipeline sinh ra với một file tham chiếu đã biết là đúng (`ok.txt`, cung cấp từ nguồn chấm) theo từng field. Toàn bộ field khớp nhau ngoại trừ `product_context.category_names`: pipeline trả về `"health_beauty"` (tiếng Anh, dịch qua `product_category_name_translation.csv`), trong khi file chuẩn trả về `"beleza_saude"` (tiếng Bồ Đào Nha, giá trị gốc trong `products.csv`). Sửa `order_product_agent.py` để lấy trực tiếp `product_category_name` từ bảng sản phẩm thay vì gọi `OlistData.get_category_english()`, sau đó chạy lại toàn bộ 50 case bằng `py main.py` (có gọi Groq API thật để sinh narrative cho `trace.jsonl`) và đóng gói lại file nộp.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `products.csv` (cột `product_category_name`), danh sách item do `order_items.csv` cung cấp qua `OlistData.get_items()` |
| Output | `product_context.category_names: list[str]` trong mỗi file `output/EC_0xx.json`, cap tối đa 5 phần tử |
| Module phụ thuộc | `src/data_layer.py` (`OlistData.get_product`) |
| Module sử dụng output | `src/schema.py` (`build_output`), `src/agents/verifier_agent.py` (kiểm cap) |
| Điều kiện lỗi cần xử lý | Sản phẩm không có `product_category_name` (giá trị rỗng/NaN) → loại khỏi danh sách thay vì chèn `None` |

### Cách xác minh

```bash
py main.py                 # chạy lại toàn bộ 50 case sau khi fix
py -c "
from src.data_layer import OlistData
from src.agents.verifier_agent import verify
import json, glob
data = OlistData('data')
for f in sorted(glob.glob('output/EC_*.json')):
    d = json.load(open(f, encoding='utf-8'))
    ok, issues = verify(d, data)
    assert ok, (f, issues)
print('all 50 pass verifier')
"
```

- **Kết quả mong đợi:** `category_names` của EC_001 là `["beleza_saude"]`, khớp file tham chiếu; 50/50 case pass verifier.
- **Kết quả thực tế:** Đúng như mong đợi; sau khi nộp lại, điểm từ 0đ tăng lên 67.9861đ.
- **Artifact/log:** `output/EC_001.json`, `trace.jsonl` (dòng `order_product_agent` của case EC_001), `metadata.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** README không nói rõ `product_context.category_names` nên là tên category gốc trong CSV (tiếng Bồ Đào Nha) hay bản dịch tiếng Anh (dataset Olist có sẵn `product_category_name_translation.csv` cho mục đích này), nên bản đầu tiên của pipeline mặc định dịch sang tiếng Anh cho dễ đọc.
- **Các phương án đã cân nhắc:**
  1. Giữ nguyên bản dịch tiếng Anh (`health_beauty`) — dễ đọc hơn cho người review.
  2. Dùng giá trị gốc tiếng Bồ Đào Nha (`beleza_saude`) — bám sát nguyên văn cột `product_category_name` trong `products.csv`, không qua bước biến đổi nào.
- **Phương án đã chọn:** Phương án 2 — giữ nguyên giá trị gốc.
- **Lý do:** Không có bằng chứng nào trong README yêu cầu dịch; việc dịch là một bước biến đổi dữ liệu ngoài phạm vi được giao (README nói "mọi số liệu... do code Python thuần, xác định tính ra từ CSV", không đề cập đến việc ánh xạ ngôn ngữ). Khi có file tham chiếu để đối chiếu, giá trị gốc mới là giá trị đúng.
- **Bằng chứng quyết định phù hợp:** Sau khi đổi sang phương án 2 và chạy lại 50 case, điểm bài nộp tăng từ 0đ lên 67.9861đ — mức tăng lớn nhất trong toàn bộ quá trình debug, xác nhận đây là nguyên nhân chính gây hard-gate 0 điểm.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Bài nộp (`output.zip`, 50 file JSON hợp lệ về schema, evidence ID, cap) bị chấm 0 điểm trên hệ thống, không có breakdown lỗi cụ thể.
- **Lệnh hoặc bước tái hiện:** Chạy `py main.py` sinh `output/`, nén thành zip, nộp lên hệ thống chấm → nhận 0đ.
- **Nguyên nhân gốc:** `order_product_agent.py` gọi `OlistData.get_category_english()` để dịch `product_category_name` sang tiếng Anh trước khi đưa vào `category_names`, trong khi kết quả chuẩn yêu cầu giữ nguyên giá trị gốc tiếng Bồ Đào Nha từ `products.csv`. Đây là sai lệch dữ liệu ở một field cụ thể (`product_context.category_names`) xảy ra ở gần như toàn bộ 50 case (mọi case có sản phẩm thuộc category có bản dịch trong `product_category_name_translation.csv`), đủ để kích hoạt hard-gate toàn bộ bài nộp theo thang điểm của README.
- **Cách xử lý:** Sửa `order_product_agent.py` để lấy trực tiếp `p.get("product_category_name")` từ `OlistData.get_product()`, bỏ bước gọi `get_category_english()`. Chạy lại `py main.py` cho toàn bộ 50 case để tái tạo `output/`, `trace.jsonl`, `metadata.json` nhất quán với code mới.
- **Cách xác minh sau khi sửa:** So khớp `output/EC_001.json` với `ok.txt` (khớp 100% ngoại trừ `confidence`, một field không có công thức bắt buộc trong README); chạy `verifier_agent.verify()` thật trên cả 50 file, kết quả 0 issue; nộp lại bài, điểm tăng lên 67.9861đ.
- **Điều học được:** Với các trường dữ liệu mà đề bài không quy định rõ định dạng/ngôn ngữ, nguyên tắc an toàn nhất là giữ nguyên giá trị gốc từ nguồn dữ liệu thay vì tự ý biến đổi (dịch, format lại, chuẩn hóa) — mọi bước biến đổi thêm đều là một giả định có thể sai và rất khó phát hiện nếu không có case mẫu để đối chiếu.

Một blocker phụ khác đã xử lý trong cùng phiên làm việc: sau khi đã fix xong, một commit local (`af2f48b`) vô tình sửa lại `order_product_agent.py` theo hướng tái tạo đúng bug đã fix (dịch category sang tiếng Anh), khiến điểm quay lại 0đ. Do commit này chưa được push lên `origin/thaitu`, xử lý bằng `git reset --hard 45b944d` để quay về commit tốt nhất đã biết mà không ảnh hưởng lịch sử đã chia sẻ với nhóm.

## 7. Hiểu biết về luồng end-to-end

> Bộ câu hỏi mẫu trong template gốc (Crossref, vector index, freshness monitoring...) thuộc về một lab khác (RAG/data-repair), không áp dụng cho lab Multi-Agent A2A này nên đã thay bằng câu hỏi đúng ngữ cảnh pipeline thực tế.

**Câu trả lời:**

1. **Dữ liệu đi từ `input/EC_xxx.json` đến `output/EC_xxx.json` như thế nào?** Coordinator đọc `claimed_order_id` từ input, dùng nó tra cứu `OlistData` (9 CSV Olist đã được index sẵn theo order/customer/product/seller). Bốn agent domain (Customer, Order & Product, Payment, Delivery) lần lượt điều tra và bàn giao evidence có cấu trúc cho Coordinator; Policy Agent áp `EC_POLICY_V2` để ra quyết định (primary/secondary issue, refund, action); `schema.py` lắp JSON theo đúng cấu trúc và cap của README; cuối cùng Verifier Agent kiểm tra evidence ID, cap, null-handling trước khi cho phép ghi file — nếu fail, case bị raise lỗi thay vì ghi output sai.
2. **Bằng chứng nào dùng để xác nhận một case đúng?** `evidence_ids` phải resolve được vào dữ liệu CSV thật (order/item/payment/seller tồn tại, root cause code nằm trong danh sách hợp lệ) — `verifier_agent.py` kiểm tra điều này bằng regex + tra cứu trực tiếp `OlistData`, không dựa vào cảm nhận của LLM.
3. **Quality check nào khác việc build đúng schema?** Verifier còn kiểm cap mảng (5/5/3/5/5/5/5/3/3/20/5), null-handling khi order không có item (`expected_total_brl`/`difference_brl`/`reconciled` phải là `null`), `confidence` trong khoảng `[0,1]`, và `case_status` chỉ nhận 2 giá trị hợp lệ.
4. **Vì sao số liệu và quyết định phải là code xác định (deterministic), không để LLM tự quyết?** Vì output được chấm điểm dựa trên độ chính xác so với dữ liệu CSV thật; một lần sample sai của LLM có thể làm sai số tiền hoặc trách nhiệm mà không tái lập được ở lần chạy sau. LLM trong pipeline này chỉ viết narrative tiếng Việt cho `trace.jsonl`, không bao giờ chạm vào số liệu hay quyết định trong `output/`.
5. **Việc sửa lỗi được xem là thành công dựa trên artifact/metric nào?** Ba mức: (a) `verifier_agent.verify()` trả `ok=True` cho cả 50 case; (b) so khớp field-by-field với file tham chiếu `ok.txt` cho case EC_001; (c) điểm thật trên hệ thống chấm tăng từ 0đ lên 67.9861đ sau khi nộp lại — đây là bằng chứng cuối cùng và đáng tin nhất vì hai bước trên chỉ kiểm tra được tính hợp lệ, không kiểm tra được "đúng" theo đáp án chấm.

## 8. Cam kết của thành viên

> Các checkbox dưới đây là lời cam kết cá nhân — để trống, tự đọc lại toàn bộ nội dung ở trên và tick sau khi xác nhận đúng với thực tế phần việc của bạn trước khi nộp.

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Thái Tú
**Ngày xác nhận:** 2026-08-05
