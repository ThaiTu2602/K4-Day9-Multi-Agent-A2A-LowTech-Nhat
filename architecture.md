# Kiến trúc hệ multi-agent A2A — K4 Day 09

## 1. Nguyên tắc thiết kế

Bài chấm theo **exact match** trên số tiền, số giờ, ID và thứ tự mảng. Từ đó rút ra
một nguyên tắc chi phối toàn bộ kiến trúc:

> **LLM quyết định, tool tính toán.**
> Không con số nào trong output đi qua bàn phím của một model 8–9B.

Cụ thể:

| Việc | Ai làm | Vì sao |
| --- | --- | --- |
| Chọn agent nào vào cuộc | LLM (coordinator) | Quyết định điều phối thật, căn cứ `investigation_scope` |
| Chọn tool nào để gọi | LLM (4 domain agent) | Quyết định thật; chọn thiếu thì Verifier bắt lỗi |
| Tính `delivery_variance_hours`, tổng tiền, đối soát | **Tool Python** | `Decimal` + `ROUND_HALF_UP`, sai một chữ số là mất điểm |
| Phân loại primary/secondary, quy trách nhiệm, refund | LLM (policy_agent) | Suy luận nghiệp vụ thật, có rule engine phản biện |
| Đánh giá thiếu/mâu thuẫn, đề xuất bước tiếp | LLM (mọi agent) | Nội dung `missing_or_conflicting` và `next_action` của handoff |
| Sắp thứ tự mảng, cắt theo trần, ghép JSON | Code | Việc cơ học, model 9B làm chỉ tổ sai |
| Chặn 12 hard gate | Code (verifier) | Quyết định pass/fail, LLM không có quyền phủ quyết |

## 2. Sơ đồ agent và luồng handoff

```
              input/EC_xxx.json
                     │
                     ▼
        ┌────────────────────────┐
        │      COORDINATOR       │  Nemotron Nano 9B V2 (OpenRouter)
        │  quyền đọc CSV: KHÔNG  │  1 lượt LLM: lập kế hoạch điều phối
        └────────────┬───────────┘
                     │ giao việc (song song)
     ┌───────────┬───┴────────┬─────────────┐
     ▼           ▼            ▼             ▼
┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
│CUSTOMER │ │  ORDER & │ │ PAYMENT │ │ DELIVERY │   Llama 3.1 8B Instant (Groq)
│  AGENT  │ │ PRODUCT  │ │  AGENT  │ │  AGENT   │   mỗi agent 2 lượt LLM:
└────┬────┘ └────┬─────┘ └────┬────┘ └────┬─────┘   ① chọn tool  ② dựng card
     │           │            │           │
     │      ┌────┴────────────┴───────────┴────┐
     │      │   TẦNG TOOL (deterministic)      │  ← mọi con số sinh ra ở đây
     │      │   9 tool, kiểm soát quyền đọc    │
     │      └────┬────────────┬───────────┬────┘
     │           │            │           │
     └─────HandoffCard────────┴───────────┘
                     │  ticket_id · question · facts+source_ids
                     ▼  · missing_or_conflicting · next_action
        ┌────────────────────────┐
        │  COORDINATOR.merge     │  gộp bằng code, không qua LLM
        └────────────┬───────────┘
                     ▼  fact book
        ┌────────────────────────┐        ┌─────────────────────┐
        │     POLICY AGENT       │◄──────►│    RULE ENGINE      │
        │  quyền đọc CSV: KHÔNG  │  đối   │  EC_POLICY_V2       │
        │  Nemotron Nano 9B V2   │  chiếu │  (deterministic)    │
        └────────────┬───────────┘        └─────────────────────┘
                     │  lệch → trả ngược, tối đa 2 lần retry
                     │  vẫn lệch → lấy rule engine, ghi policy_override vào trace
                     ▼
        ┌────────────────────────┐
        │   ASSEMBLER (code)     │  dựng JSON + evidence_ids
        └────────────┬───────────┘
                     ▼
        ┌────────────────────────┐
        │    VERIFIER AGENT      │  Nemotron Nano 9B V2
        │  lớp 1: 12 hard gate   │  ← quyết định pass/fail
        │  lớp 2: LLM soi ngữ nghĩa │ ← ghi trace, không phủ quyết
        └────────────┬───────────┘
                     ▼
              output/EC_xxx.json
              logging/trace.jsonl
```

## 3. Vai trò và quyền truy cập dữ liệu

Phân quyền là **ràng buộc thực thi**, không phải mô tả trên giấy. Mỗi tool khai báo
nó cần đọc bảng nào (`src/tools/registry.py`), mỗi agent khai báo nó được đọc bảng
nào (`src/config.py: AGENTS[...].allowed_tables`). Gọi ngoài quyền → `ToolAccessError`,
chương trình dừng chứ không âm thầm chạy sai.

| Agent | Model | Provider | Bảng được đọc | Tool sở hữu |
| --- | --- | --- | --- | --- |
| `coordinator` | Nemotron Nano 9B V2 | OpenRouter | **không có** | — |
| `customer_agent` | Llama 3.1 8B Instant | Groq | customers, orders | `get_customer_identity`, `get_customer_order_history` |
| `order_product_agent` | Llama 3.1 8B Instant | Groq | orders, order_items, products, sellers, category_translation | `get_order_header`, `get_order_items`, `get_product_context` |
| `payment_agent` | Llama 3.1 8B Instant | Groq | order_payments, order_items | `get_payment_rows`, `reconcile_payments` |
| `delivery_agent` | Llama 3.1 8B Instant | Groq | orders, order_items | `get_delivery_timestamps`, `analyze_seller_handoff` |
| `policy_agent` | Nemotron Nano 9B V2 | OpenRouter | **không có** | — |
| `verifier_agent` | Nemotron Nano 9B V2 | OpenRouter | tất cả (chỉ đọc, để kiểm tra ID có thật) | — |

`coordinator` và `policy_agent` **bị cắt quyền đọc CSV có chủ đích**. Policy Agent chỉ
được kết luận từ handoff card của agent khác — đó là điểm cốt lõi của đề bài: có phân
công, có bàn giao, có kiểm chứng, không phải một prompt làm tất.

Mọi model đều ≤ 10B tham số. `ModelSpec.__post_init__` ném lỗi nếu ai đó thêm model
vượt trần, nên không thể vi phạm ràng buộc này mà không biết.

## 4. Hợp đồng handoff (A2A envelope)

Mọi thứ đi giữa hai agent đều là một `HandoffCard` (`src/contracts.py`):

```json
{
  "ticket_id": "EC_002",
  "from_agent": "delivery_agent",
  "to_agent": "coordinator",
  "question": "Đơn có giao trễ không, seller nào bàn giao sau shipping_limit_date?",
  "facts": [
    { "key": "delivery_variance_hours", "value": 87.39,
      "source_ids": ["order:eb09635680fadffb33358e40b05c9029"] },
    { "key": "late_handoff_seller_ids", "value": ["c3867b4666c7d76867627c2f7fb22e21"],
      "source_ids": ["seller:c3867b4666c7d76867627c2f7fb22e21"] }
  ],
  "missing_or_conflicting": [
    { "field": "carrier_handoff_at", "reason": "NULL trong CSV", "impact": "handoff variance = null" }
  ],
  "next_action": "coordinator: chuyển late_handoff_seller_ids cho policy_agent"
}
```

Hai quy tắc bắt buộc:

1. **`facts` do code gắn từ kết quả tool, LLM không được gõ lại.** Nếu để model chép
   `87.39` nó có thể ra `87.4`. LLM chỉ viết `question`, `missing_or_conflicting`,
   `next_action`, `notes`.
2. **Mọi fact phải có `source_ids`.** Fact không nguồn bị Verifier từ chối. Chính
   `source_ids` là nguyên liệu sinh `evidence_ids` cuối cùng.

## 5. Vòng kiểm chứng Policy Agent ↔ Rule Engine

Đây là cơ chế verification giữa các agent, không phải hình thức:

```
Policy Agent đề xuất  →  Rule engine replay EC_POLICY_V2 trên CÙNG fact book
                          ├─ khớp  → nhận kết luận của agent
                          ├─ lệch  → trả ngược kèm đúng điểm lệch, agent làm lại
                          │          (tối đa 2 lần)
                          └─ vẫn lệch → lấy rule engine, ghi policy_override vào trace
```

Vòng này bắt được lỗi thật. Ví dụ đo được trong lúc phát triển: với EC_047, Nemotron
ghi `"related_order_count": 1` rồi kết luận `"repeat_customer": false` — đọc đúng số
nhưng so sánh sai. Tỷ lệ đồng thuận giữa agent và rule engine được ghi vào
`logging/metadata.json` sau mỗi lượt chạy.

Để giảm loại lỗi này, Policy Agent bị bắt **viết ra phép so sánh trước khi kết luận**:
mỗi secondary issue phải điền `value`, `rule`, `result` riêng từng dòng. Danh sách
`secondary_issues` và `resolution_actions` cuối cùng được code ghép lại từ chính các
`result` đó, theo đúng thứ tự nghiệp vụ — LLM lo phần xét đoán, code lo phần sắp xếp.

## 6. Đường chạy tham chiếu

`src/reference.py` chạy đúng 9 tool đó + rule engine, **không gọi LLM**, sinh ra 50
output trong khoảng 3 giây. Nó có hai vai trò:

- **Mốc so sánh**: sau mỗi lượt chạy agent, orchestrator tự động diff sâu từng field
  của 50 output với mốc này. Lệch khác 0 là có bug, in ra ngay.
- **Kiểm tra nhanh không tốn token**: `python -m src.reference --summary`.

Hệ thống vì thế không cần hardcode đáp án nào: mốc tham chiếu được sinh từ CSV và
bảng luật trong README, không phải từ một file đáp án.

**Kiểm chứng độc lập**: ví dụ ở README mục 6 chính là case EC_002 của bộ đề. Toàn bộ
số liệu của đường tham chiếu khớp tuyệt đối với ví dụ đó — `delivery_variance_hours`
87.39, `handoff_variance_hours` 1.04, `item_total_brl` 194.0, `freight_total_brl`
18.27, `expected_total_brl` 212.27, `difference_brl` 0.0, refund 18.27, và
`resolution_actions` ra đúng `[refund_freight, review_seller_handoff,
verify_payment_allocation]`. Đây là bằng chứng bốn công thức và bảng luật action đã
được cài đúng.

## 7. 12 hard gate

| Gate | Nội dung |
| --- | --- |
| G1 | `case_id` khớp tên file |
| G2 | Đủ key bắt buộc, đúng kiểu dữ liệu |
| G3 | `evidence_id` khớp đúng 5 regex cho phép |
| G4 | Evidence tồn tại thật trong CSV |
| G5 | Mọi order/item/payment/seller/product ID truy ngược được về CSV |
| G6 | Trần độ dài 11 mảng |
| G7 | `confidence ∈ [0,1]` |
| G8 | Timestamp đúng `YYYY-MM-DD HH:MM:SS` hoặc `null` |
| G9 | Quy tắc null: 6 case không có item row, 14 case không có ngày giao |
| G10 | Enum + `case_status` ⟺ `refund > 0` + thứ tự secondary issue |
| G11 | `related_order_ids` không chứa `claimed_order_id`, không trùng lặp |
| G12 | Mọi số tiền và số giờ đúng 2 chữ số thập phân |

## 8. Xử lý hạn mức nhà cung cấp

Đo từ header thật:

- **Groq** `llama-3.1-8b-instant`: 14400 request/ngày nhưng **6000 token/phút** — nút
  thắt là token. `x-ratelimit-reset-tokens: 410ms` sau khi dùng 41 token cho thấy đây
  là bucket nạp lại liên tục ở 100 token/giây, nên `src/agents/ratelimit.py` dùng
  token bucket chứ không phải cửa sổ trượt 60 giây. Bản cửa sổ trượt đầu tiên đo được
  1326 giây nằm chờ trên 40 lượt gọi, trong khi thời gian HTTP thật chỉ 0.9 giây/lượt.
- **OpenRouter** bản `:free`: giới hạn theo số request mỗi phút.

Khi một provider trả 429/402, agent chuyển sang model ở **provider còn lại** và ghi
`model_fallback` vào trace. `logging/metadata.json` báo cáo model **đã thực sự chạy**
(đọc lại từ trace), không phải model được cấu hình — nếu có fallback thì file khai báo
đúng như vậy.

Cache theo `hash(model, prompt)` trong `.cache/` khiến lần chạy lại gần như miễn phí.

## 9. Tham số chạy

| Tham số | Giá trị | Lý do |
| --- | --- | --- |
| `temperature` | 0.0 | Chấm exact match, mọi nguồn ngẫu nhiên đều là rủi ro |
| `top_p` | 1.0 | Đã greedy thì không cắt phân phối |
| `seed` | 42 | Groq hỗ trợ; hai lần chạy ra cùng kết quả |
| `response_format` | `json_object` | Model nhỏ hay bọc JSON trong khối code |
| Nemotron reasoning | `/no_think` | Đo được: `/think` ăn hết `max_tokens` rồi bị cắt giữa chừng nên JSON không đóng, parse hỏng 100%. Nâng lên 3500 token thì parse được nhưng chậm 4–5 lần mà **không** chính xác hơn |
| `CONCURRENCY` | 4 | Cân giữa TPM của Groq và RPM của OpenRouter |

## 10. Cấu trúc mã nguồn

```
src/
  config.py          model, provider, phân quyền agent, tham số chạy
                     (nguồn chân lý duy nhất, metadata.json sinh từ đây)
  contracts.py       CaseTicket, Fact, Gap, HandoffCard, PolicyDecision
  loader.py          đọc 9 CSV → index → OrderBundle
  numeric.py         Decimal + ROUND_HALF_UP cho tiền và giờ
  reference.py       đường chạy tham chiếu không LLM
  orchestrator.py    điểm vào, chạy song song, diff, sinh metadata
  trace.py           ghi trace.jsonl (mode 'w', chỉ giữ lượt chạy mới nhất)
  tools/
    registry.py      danh mục 9 tool + kiểm soát quyền truy cập
    customer_tools.py  order_tools.py  payment_tools.py  delivery_tools.py
  policy/
    taxonomy.py      enum và thứ tự ưu tiên của EC_POLICY_V2
    rules.py         rule engine + diff_decisions
    assembler.py     dựng output JSON + evidence_ids
    schema.py        12 hard gate
    limits.py        trần độ dài mảng
  agents/
    llm.py           client 2 provider (chỉ thư viện chuẩn), retry, cache, JSON mode
    ratelimit.py     token bucket theo provider
    base.py          khung agent, fallback khi hết quota
    coordinator.py  domain.py  policy_agent.py  verifier_agent.py
tests/               unit test cho rule engine và null handling
```

Không dùng thư viện bên thứ ba, chỉ thư viện chuẩn của Python. Trong một cuộc thi
4 tiếng, mỗi dependency là thêm một chỗ có thể vỡ.

## 11. Lệnh chạy

```bash
cp .env.example .env          # rồi dán OPENROUTER_API_KEY và GROQ_API_KEY

python3 -m src.reference --summary       # kiểm tra tầng dữ liệu + luật, không tốn token
python3 -m src.reference --write output  # sinh 50 output bằng đường tham chiếu
python3 -m src.orchestrator              # chạy đầy đủ hệ agent trên 50 case
python3 -m src.orchestrator --limit 3    # thử nhanh 3 case
python3 -m pytest tests -q               # unit test
```
