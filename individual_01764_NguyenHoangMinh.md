# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung          |
| --------------- | ----------------- |
| Họ và tên       | Nguyễn Hoàng Minh |
| MSSV            | 2A202601764       |
| Khóa/Lớp        | K4                |
| Vai trò chính   | Tự build toàn bộ pipeline (nhóm thống nhất mỗi người build độc lập rồi so điểm, lấy bản cao nhất) |
| Ngày hoàn thành | 2026-08-05        |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

Nhóm chọn cách làm: mỗi thành viên tự build một bản hoàn chỉnh, sau đó so điểm và lấy
bản cao nhất làm bản nộp. Vì vậy tôi sở hữu toàn bộ pipeline dưới đây.

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data pipeline | `src/loader.py` (`OlistStore`, `build_bundle`) | 7 file CSV Olist | `OrderBundle` bất biến cho từng order | Hoàn thành |
| Số học tiền và thời gian | `src/numeric.py` (`money`, `hours_between`, `dsum`) | `Decimal` từ CSV, `datetime` | float đã làm tròn 2 chữ số ROUND_HALF_UP | Hoàn thành |
| Tầng tool + phân quyền | `src/tools/` (9 tool, `registry.assert_can_use`) | `OrderBundle` | `list[Fact]` kèm `source_ids` | Hoàn thành |
| Rule engine EC_POLICY_V2 | `src/policy/rules.py`, `taxonomy.py` | fact book | `PolicyDecision` | Hoàn thành |
| Assembler + evidence | `src/policy/assembler.py` | fact book + `PolicyDecision` | JSON đúng schema README mục 6 | Hoàn thành |
| 12 hard gate | `src/policy/schema.py` (`validate_output`) | JSON output | `list[Violation]` | Hoàn thành |
| Client LLM 2 provider | `src/agents/llm.py` | prompt | JSON đã parse + số token | Hoàn thành |
| Rate limiter | `src/agents/ratelimit.py` (`TokenBucketLimiter`) | ước lượng token | quyền gọi API | Hoàn thành |
| 7 agent + handoff A2A | `src/agents/` | `CaseTicket` | `HandoffCard`, `PolicyDecision` | Hoàn thành |
| Orchestrator + diff | `src/orchestrator.py` | 50 file input | 50 file output, `trace.jsonl`, `metadata.json` | Hoàn thành |
| Đường chạy tham chiếu | `src/reference.py` | 50 file input | 50 output mốc so sánh, không gọi LLM | Hoàn thành |
| Unit test | `tests/test_rules.py`, `tests/test_pipeline.py` | — | 182 test | Hoàn thành |
| Tài liệu kiến trúc | `architecture.md` | — | Sơ đồ agent, phân quyền, luồng handoff | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Chia sẻ phát hiện "ví dụ README mục 6 chính là EC_002" | Cả nhóm | Nhóm có một ground truth thật để đối chiếu 4 công thức và bảng luật action, thay vì đoán |
| Chia sẻ hai cái bẫy hạn mức đo được từ header | Cả nhóm | Groq giới hạn 6000 token/phút chứ không phải số request; `User-Agent` mặc định của urllib bị Cloudflare chặn 403 code 1010 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Sinh 50 output đúng schema | `output/EC_001..050.json` | 50 file, 50/50 qua hard gate | `python3 -m src.reference --summary` |
| Cài 12 hard gate | `src/policy/schema.py` | 0 vi phạm trên cả 50 case | `python3 -m pytest tests -q` → 182 passed |
| Dựng hệ 7 agent có handoff và kiểm chứng | `src/agents/`, `logging/trace.jsonl` | Trace ghi từng bước của từng agent | `python3 -m src.orchestrator` |
| Đối chiếu output agent với mốc tham chiếu | `orchestrator.diff_documents` | Lệch = 0 trên các case đã chạy | Dòng "Lech so voi tham chieu" trong log chạy |
| Khoá ground truth bằng test | `tests/test_pipeline.py::test_ec_002_khop_tung_con_so_cua_vi_du_readme` | Test pass | `pytest tests -q` |

Một output cụ thể mà phần việc của tôi tạo ra và giúp xác minh:

Case **EC_002**. Trong lúc kiểm tra tôi phát hiện ví dụ minh hoạ ở README mục 6 không
phải số bịa mà chính là case EC_002 của bộ đề. Output pipeline của tôi trùng khớp tuyệt
đối với ví dụ đó ở mọi trường số: `delivery_variance_hours` 87.39,
`handoff_variance_hours` 1.04, `item_total_brl` 194.0, `freight_total_brl` 18.27,
`expected_total_brl` 212.27, `payment_total_brl` 212.27, `difference_brl` 0.0,
`payment_types` `["credit_card","voucher"]`, refund 18.27, và `resolution_actions` ra
đúng `["refund_freight","review_seller_handoff","verify_payment_allocation"]`.

Đây là bằng chứng độc lập rằng bốn công thức (delivery variance, handoff variance,
expected total, difference) và bảng điều kiện kích hoạt action đã được cài đúng, chứ
không phải tôi tự khẳng định. Tôi khoá phát hiện này lại bằng một test riêng để nếu ai
sửa công thức thì test đỏ ngay.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Đề bài chấm theo exact match trên số tiền, số giờ, ID và thứ tự mảng, đồng thời bắt
buộc mỗi agent chỉ được dùng model ≤ 10B tham số. Hai ràng buộc này xung đột trực tiếp:
một model 8–9B không đủ tin cậy để tính `(delivered − estimated) / 3600` làm tròn 2 chữ
số, và cũng không đáng tin để chép lại một `order_id` dài 32 ký tự hex mà không sai.

Nếu để LLM tính số thì mất điểm ở 4 trên 7 ô rubric. Nếu bỏ LLM đi thì vi phạm tinh
thần đề bài, vì README nói rõ "không có điểm cho việc chỉ đặt tên nhiều agent nhưng
toàn bộ xử lý nằm trong một prompt duy nhất".

### Cách triển khai

Nguyên tắc tôi chọn: **LLM quyết định, tool tính toán.**

LLM thật sự ra quyết định ở bốn chỗ, và mỗi quyết định đều có hệ quả kiểm chứng được:

1. **Coordinator chọn agent nào vào cuộc**, căn cứ `investigation_scope` của ticket.
2. **Bốn domain agent tự chọn tool cần gọi** trong danh mục chúng được phép. Chọn thiếu
   thì fact thiếu và Verifier bắt lỗi; chọn tool ngoài quyền thì `ToolAccessError` làm
   chương trình dừng chứ không âm thầm chạy sai.
3. **Policy Agent phân loại nghiệp vụ**: primary issue, secondary issue, quy trách
   nhiệm, refund, action.
4. **Mọi agent tự đánh giá** fact nào còn thiếu hoặc mâu thuẫn, và đề xuất bước tiếp
   cho agent nhận việc.

Tool Python lo phần còn lại. Ba quyết định kỹ thuật ở tầng này:

- **Tiền tính bằng `Decimal`, không dùng `float`.** `194.00 + 18.27` với float cho
  `212.27000000000001`, đủ để `difference_brl` lệch khỏi `0.0`.
- **Làm tròn bằng `ROUND_HALF_UP`, không dùng `round()`.** `round()` của Python là
  banker's rounding: `round(2.675, 2)` cho `2.67` chứ không phải `2.68`.
- **Thứ tự mảng chuẩn hoá một lần ở loader**: item theo `order_item_id`, payment theo
  `payment_sequential`, `related_order_ids` theo đúng thứ tự dòng trong
  `olist_orders_dataset.csv`.

Chống bịa số liệu: trong `HandoffCard`, trường `facts` do **code** gắn từ kết quả tool,
LLM không được gõ lại. LLM chỉ viết `question`, `missing_or_conflicting`, `next_action`,
`notes`. Nếu để model chép `87.39` nó có thể ra `87.4`.

Kiểm chứng giữa các agent: Policy Agent đề xuất trước, rule engine replay
EC_POLICY_V2 trên **cùng** fact book để phản biện. Lệch thì trả ngược kèm đúng điểm
lệch cho agent sửa, tối đa 2 lần; vẫn lệch thì lấy rule engine và ghi
`policy_override` vào trace. Tỷ lệ đồng thuận được báo cáo trong `metadata.json`, không
giấu.

Phân quyền dữ liệu là ràng buộc thực thi chứ không phải mô tả trên tài liệu. Mỗi tool
khai báo nó đọc bảng nào, mỗi agent khai báo nó được đọc bảng nào. `coordinator` và
`policy_agent` có `allowed_tables` **rỗng** — chúng không thể tự tra CSV, buộc phải kết
luận từ handoff card của agent khác.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `input/EC_xxx.json` → `CaseTicket(case_id, claimed_order_id, include_customer_history, include_product_context, policy_version)` |
| Output | `output/EC_xxx.json` đúng schema README mục 6, 11 khoá cấp một |
| Contract nội bộ | `HandoffCard(ticket_id, from_agent, to_agent, question, facts[key/value/source_ids], missing_or_conflicting[field/reason/impact], next_action)` |
| Module phụ thuộc | `loader` → `tools` → `agents`; `numeric` dùng bởi `tools`; `taxonomy` dùng bởi `rules` và `schema` |
| Module sử dụng output | `policy/assembler` dựng JSON, `policy/schema` chặn hard gate, `orchestrator` ghi file và diff |
| Điều kiện lỗi cần xử lý | order không tồn tại trong CSV; order không có item row (6/50 case); không có `order_delivered_customer_date` (14/50 case); không có `order_delivered_carrier_date` (13/14 case chưa giao); nhiều item trỏ về cùng product (21/50 case); LLM trả JSON hỏng; provider trả 429/402; Cloudflare chặn 403 |

### Cách xác minh

```bash
# 1. Tầng dữ liệu + rule engine, không tốn token
python3 -m src.reference --summary

# 2. Unit test
python3 -m pytest tests -q

# 3. Hệ agent đầy đủ, tự diff với mốc tham chiếu
python3 -m src.orchestrator --concurrency 4

# 4. Kiểm tra zip nộp bài đúng 50 file, không file lạ
unzip -l output.zip | grep -c 'EC_.*json'
```

- **Kết quả mong đợi:** 50/50 case qua hard gate; toàn bộ test pass; output hệ agent
  không lệch so với đường tham chiếu; zip chứa đúng 50 file.
- **Kết quả thực tế:**
  - Lệnh 1: `HARD GATE: 50/50 case sach`, chạy hết 2.9 giây.
  - Lệnh 2: `182 passed in 2.89s`.
  - Lệnh 3: đang chạy tại thời điểm viết báo cáo. Trên các case đã hoàn tất, hard gate
    đạt 100% và số điểm lệch so với đường tham chiếu là **0**. Đồng thuận giữa Policy
    Agent và rule engine chưa đạt 100% — con số cuối cùng lấy từ
    `logging/metadata.json` sau khi chạy xong. Tôi **không** ghi "đã chạy thành công
    toàn bộ 50 case bằng hệ agent" vì tại thời điểm nộp báo cáo lượt chạy đó chưa kết
    thúc.
  - Lệnh 4: `50`.
- **Artifact/log:** `logging/trace.jsonl`, `logging/metadata.json`, `output/`,
  `output.zip`. Không file nào chứa secret; `.env` nằm trong `.gitignore` và đã kiểm
  tra bằng `git check-ignore .env` trước khi commit.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Ai chịu trách nhiệm cho những con số cuối cùng trong output — LLM hay
  code? Đề bài vừa chấm exact match, vừa yêu cầu kiến trúc multi-agent thật.

- **Các phương án đã cân nhắc:**
  1. *LLM làm tất*: đưa dữ liệu order vào prompt, để model tự tính variance, tự cộng
     tiền, tự viết JSON. Đúng tinh thần "agent" nhất nhìn từ bên ngoài.
  2. *Code làm tất*: bỏ LLM, chỉ chạy rule engine. Chắc chắn đúng nhưng vi phạm yêu cầu
     multi-agent của đề.
  3. *Tách vai*: LLM điều phối, chọn tool, phân loại nghiệp vụ và đánh giá; tool
     deterministic tính mọi con số; rule engine phản biện phần phân loại của LLM.

- **Phương án đã chọn:** phương án 3.

- **Lý do:** Phương án 1 hỏng ngay ở khâu đo. Tôi đã thử cho Nemotron Nano 9B V2 tự
  đưa ra kết luận nghiệp vụ trên fact book và nó sai ở những chỗ rất cơ bản — với
  EC_047 nó ghi đúng `"related_order_count": 1` rồi kết luận `"repeat_customer": false`.
  Nó đọc đúng số nhưng so sánh sai. Một model như vậy không thể được giao việc tính
  `87.3925 → 87.39`. Phương án 2 thì bỏ mất phần đề bài chấm điểm. Phương án 3 giữ
  được cả hai: LLM vẫn ra quyết định thật ở bốn chỗ và những quyết định đó có hệ quả
  kiểm chứng được, còn độ chính xác số học được bảo đảm bởi `Decimal` và rule engine.

- **Bằng chứng quyết định phù hợp:** Đường tham chiếu (tool + rule engine) cho 50/50
  case sạch hard gate và khớp tuyệt đối với ví dụ README mục 6. Output của hệ agent
  diff bằng 0 so với mốc đó trên mọi case đã chạy. Ngược lại, vòng đối chiếu bắt được
  lỗi phân loại thật của LLM trên nhiều case — nếu tin LLM hoàn toàn thì những case đó
  đã sai `secondary_issues` và `resolution_actions`, tức mất điểm ở hai ô rubric.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Toàn bộ lượt gọi tới Groq đều hỏng với
  `HTTP 403 tu groq: error code: 1010`, trong khi cùng request đó chạy bằng `curl` lại
  trả 200 bình thường. Trace ghi hàng loạt dòng `llm_error` cho cả bốn domain agent.

- **Lệnh hoặc bước tái hiện:**
  ```bash
  python3 -m src.orchestrator --cases EC_002 --concurrency 1
  python3 -c "import json; [print(json.loads(l).get('error','')[:80]) for l in open('logging/trace.jsonl')]"
  ```

- **Nguyên nhân gốc:** Không phải lỗi API key hay quyền. Cloudflare đứng trước Groq
  chặn `User-Agent` mặc định của `urllib` (`Python-urllib/3.13`); mã 1010 của Cloudflare
  nghĩa là "chặn theo chữ ký trình duyệt". `curl` chạy được vì nó gửi `User-Agent`
  riêng. Triệu chứng dễ bị chẩn đoán nhầm thành hết quota hoặc sai key, và tôi suýt đi
  sai hướng vì `403` thường gợi ý vấn đề xác thực.

- **Cách xử lý:** Đặt `User-Agent` và `Accept` tường minh trong `_headers()` của
  `src/agents/llm.py`, kèm bình luận giải thích để người sau không xoá nhầm.

- **Cách xác minh sau khi sửa:** Chạy lại `python3 -m src.orchestrator --cases EC_002`.
  Trace không còn dòng `llm_error` nào từ Groq; các lượt gọi trả về với
  `parsed_ok: true` và `latency_ms` khoảng 900ms.

- **Điều học được:** Khi một request chạy được bằng `curl` mà hỏng trong code, phải so
  sánh **header** trước khi nghi ngờ xác thực. Bài học thứ hai quan trọng hơn: nhờ
  thiết kế mọi lỗi LLM đều được nuốt lại và ghi vào trace thay vì ném ra ngoài, hệ thống
  vẫn chạy hết 50 case và tôi có đủ dữ liệu để chẩn đoán. Nếu để exception làm sập
  chương trình ở case đầu tiên, tôi chỉ có một stack trace thay vì một bảng thống kê.

Một blocker thứ hai cùng loại, đáng ghi lại vì cách chẩn đoán giống nhau: sau khi sửa
403, hệ thống chạy đúng nhưng cực chậm, 173 giây cho một case. Nghi ngờ đầu tiên là
model chậm. Nhưng vì trace tách riêng `latency_ms` (thời gian HTTP thật) và
`throttle_wait_ms` (thời gian nằm chờ rate limiter), số liệu cho thấy HTTP chỉ 0.9 giây
median, còn 1326 giây là nằm chờ. Nguyên nhân: tôi cài rate limiter theo cửa sổ trượt
60 giây, trong khi header `x-ratelimit-reset-tokens: 410ms` sau khi dùng 41 token cho
thấy Groq dùng bucket nạp lại liên tục ở 100 token/giây. Sửa sang token bucket đúng cơ
chế thì chỉ phải chờ đúng phần token chưa kịp nạp lại.

## 7. Hiểu biết về luồng end-to-end

> Ghi chú: năm câu hỏi trong mẫu (Crossref, vector index, retrieval quality, corrupted
> và repaired test set) thuộc bài lab Day 8 về RAG pipeline, không áp dụng cho Day 9.
> Tôi trả lời phần tương ứng của Day 9 theo đúng tinh thần từng câu hỏi.

**1. Dữ liệu đi từ CSV Olist đến output như thế nào?**

`OlistStore` đọc 7 file CSV cần thiết một lần khi khởi động và dựng index trong RAM
(order theo `order_id`, item và payment theo `order_id`, customer theo `customer_id`,
và một map `customer_unique_id → danh sách order_id` giữ đúng thứ tự dòng trong CSV).
Tôi cố tình không nạp `olist_geolocation_dataset.csv` (61 MB) và
`olist_order_reviews_dataset.csv` vì không trường nào của output schema cần tới chúng.

Với mỗi case, `build_bundle(order_id)` gom mọi thứ liên quan tới order đó thành một
`OrderBundle` bất biến. Đây là đơn vị dữ liệu duy nhất mà tầng tool được đọc; agent
không bao giờ chạm trực tiếp vào CSV. Chín tool biến `OrderBundle` thành `list[Fact]`,
mỗi fact kèm `source_ids`. Coordinator gộp các fact thành fact book, Policy Agent kết
luận, assembler dựng JSON, Verifier chặn hard gate, rồi mới ghi file.

**2. Cái gì đóng vai ground truth để đo chất lượng?**

Bài này không phát ground truth. Tôi tạo ra hai nguồn đối chiếu độc lập:

- *Ví dụ ở README mục 6* hoá ra chính là case EC_002. Đây là ground truth thật cho bốn
  công thức và bảng điều kiện action, và tôi khoá nó bằng một unit test.
- *Đường chạy tham chiếu* `src/reference.py` chạy tool + rule engine không qua LLM. Sau
  mỗi lượt chạy hệ agent, orchestrator diff sâu từng field của 50 output với mốc này.
  Lệch khác 0 nghĩa là có bug ở tầng agent.

**3. Hard gate khác gì kiểm chứng ngữ nghĩa?**

Đây là hai lớp khác hẳn nhau về thẩm quyền. Hard gate là 12 nhóm kiểm tra
deterministic: ID có tồn tại trong CSV không, mảng có vượt trần không, timestamp đúng
định dạng chưa, quy tắc null đã đúng chưa. Lớp này **quyết định** được ghi file hay
không, vì đề nói case dính hard gate nhận 0 điểm. Kiểm chứng ngữ nghĩa là lớp LLM của
Verifier, đi tìm mâu thuẫn mà regex không thấy được, ví dụ kết luận quy trách nhiệm cho
seller nhưng `late_handoff_seller_ids` lại rỗng. Nhận xét của lớp này được ghi vào trace
để đọc lại, nhưng **không** có quyền phủ quyết — một model 9B không được lật ngược một
bộ kiểm tra đã chạy đúng.

**4. Vì sao phải dùng cùng một fact book cho Policy Agent và rule engine?**

Vì nếu hai bên nhìn dữ liệu khác nhau thì phép so sánh vô nghĩa: không phân biệt được
LLM suy luận sai hay chỉ là nó thiếu dữ liệu. Rule engine vì thế nhận đúng fact book mà
Policy Agent nhận, không đọc CSV. Khi phát hiện lệch, tôi biết chắc đó là lỗi suy luận
và có thể trả ngược đúng điểm lệch cho agent sửa.

**5. Dựa vào artifact và metric nào để coi là chạy thành công?**

Bốn điều kiện, tất cả đều kiểm tra được:

1. `output/` có đúng 50 file, 0 vi phạm hard gate.
2. Diff giữa output hệ agent và đường tham chiếu bằng 0.
3. `pytest tests -q` xanh toàn bộ.
4. `logging/trace.jsonl` có đủ 50 case với dòng `case_done`, và `metadata.json` khai
   báo đúng model đã thực sự chạy — số liệu này đọc ngược từ trace chứ không lấy từ
   cấu hình, nên nếu có fallback sang provider khác thì file khai báo đúng như vậy.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Hoàng Minh
**Ngày xác nhận:** 2026-08-05
