# Architecture — Multi-Agent E-commerce Dispute Resolution

## 1. Tổng quan luồng xử lý

```
input/EC_xxx.json
        │
        ▼
┌───────────────────┐
│    Coordinator     │  (src/coordinator.py)
│  process_case()    │
└─────────┬──────────┘
          │ claimed_order_id
          ▼
   OlistData (src/data_layer.py)
   9 CSV Olist, indexed theo order_id / customer_id / product_id / seller_id
          │
          ├──► Customer Agent ───────► {customer_unique_id, related_order_ids, repeat_customer}
          │
          ├──► Order & Product Agent ─► {items, seller_ids, product_ids, category_names,
          │                              multi_item_order, multi_seller_order, multiple_categories}
          │
          ├──► Payment Agent ─────────► {item_total, freight_total, expected_total, payment_total,
          │      (dùng items từ Order&Product)   difference, reconciled, payment_types, split_payment}
          │
          ├──► Delivery Agent ────────► {delivery_variance_hours, seller_handoff_analysis,
          │      (dùng items từ Order&Product)   late_handoff_seller_ids, is_late}
          │
          ▼
   Coordinator gộp evidence bundle từ 4 agent trên
          │
          ▼
   Policy Agent (src/agents/policy_agent.py)
   Áp EC_POLICY_V2 theo đúng thứ tự ưu tiên → primary_issue, root_cause_code,
   responsible_parties, refund, secondary_issues, resolution_actions
          │
          ▼
   Schema builder (src/schema.py)
   Lắp JSON theo schema output, áp mọi giới hạn mảng (5/5/3/5/5/5/5/3/3/20/5)
          │
          ▼
   Verifier Agent (src/agents/verifier_agent.py)
   Kiểm evidence ID có tồn tại thật trong CSV, kiểm cap, null handling,
   confidence range, case_status hợp lệ → pass/fail
          │
          ▼
   output/EC_xxx.json  +  1 dòng trace.jsonl cho mỗi bước handoff
```

Mỗi case đi tuần tự qua 6 agent; mỗi agent handoff một payload dữ liệu có cấu trúc (structured data) cho Coordinator, kèm một câu tường thuật ngắn (narrative) do model LLM sinh ra để log vào `trace.jsonl` — đúng tinh thần A2A (agent-to-agent handoff) thay vì gộp toàn bộ logic vào một prompt.

## 2. Vai trò và quyền truy cập từng agent

| Agent | File | Dữ liệu được đọc | Output bàn giao cho Coordinator |
|---|---|---|---|
| **Coordinator** | `src/coordinator.py` | Không đọc CSV trực tiếp; nhận input case, gọi các agent theo thứ tự, ghi `trace.jsonl` | JSON output cuối cùng của case |
| **Customer Agent** | `src/agents/customer_agent.py` | `customers.csv`, `orders.csv` (qua `OlistData`) | `customer_unique_id`, `related_order_ids`, cờ `repeat_customer` |
| **Order & Product Agent** | `src/agents/order_product_agent.py` | `order_items.csv`, `sellers.csv`, `products.csv`, `product_category_name_translation.csv` | danh sách item/seller/product/category, cờ `multi_item_order`/`multi_seller_order`/`multiple_categories` |
| **Payment Agent** | `src/agents/payment_agent.py` | `order_payments.csv` + item list do Order&Product Agent bàn giao (không tự đọc lại `order_items.csv`) | tổng tiền item/freight/expected/payment, `difference_brl`, `reconciled`, `payment_types`, cờ `split_payment` |
| **Delivery Agent** | `src/agents/delivery_agent.py` | timestamp trong `orders.csv` + item list (seller_id, shipping_limit_date) do Order&Product Agent bàn giao | `delivery_variance_hours`, `seller_handoff_analysis` theo từng seller, `late_handoff_seller_ids`, cờ `is_late` |
| **Policy Agent** | `src/agents/policy_agent.py` | Không đọc CSV; chỉ nhận evidence bundle từ 4 agent trên | `primary_issue`, `root_cause_code`, `responsible_parties`, `recommended_refund_brl`, `secondary_issues`, `resolution_actions`, `case_status`, `confidence` |
| **Verifier Agent** | `src/agents/verifier_agent.py` | `OlistData` (để đối chiếu evidence ID có tồn tại thật) + JSON output đã lắp ráp | `(ok: bool, issues: list[str])`; nếu `ok=False`, case bị raise lỗi thay vì ghi file sai |

Nguyên tắc phân quyền: mỗi agent chỉ đọc đúng domain dữ liệu của mình; các agent phụ thuộc dữ liệu chung (item list) nhận lại qua handoff từ Order & Product Agent thay vì tự parse CSV lần nữa, tránh hai nguồn sự thật (single source of truth) cho cùng một bảng.

## 3. Nguyên tắc thiết kế: tách rời "tính toán" và "diễn giải"

- Mọi số liệu và quyết định được ghi vào `output/` (variance giờ, số tiền, `primary_issue`, `refund`, evidence ID...) đều do **code Python thuần, xác định (deterministic)** tính ra từ CSV — không đi qua LLM. Điều này đảm bảo tái lập được và không có rủi ro hallucination ảnh hưởng điểm số.
- Model LLM (`llama-3.1-8b-instant`, 8B tham số, gọi qua Groq API — xem `src/llm_client.py`) chỉ được dùng để mỗi agent viết **một câu tường thuật ngắn bằng tiếng Việt** tóm tắt phát hiện của mình, ghi vào `trace.jsonl` để thể hiện quá trình điều tra/handoff giữa các agent. Câu này không bao giờ được ghi vào `output/EC_xxx.json`.
- Nếu Groq API không phản hồi được, Coordinator vẫn tiếp tục pipeline với một narrative fallback (đánh dấu `llm_used: false` trong trace) — pipeline không phụ thuộc cứng vào tính khả dụng của LLM để ra kết quả đúng.

## 4. Quyết định thiết kế đáng chú ý (do README để ngỏ)

README không nêu rõ chính xác secondary issue nào kích hoạt action bổ sung nào, chỉ nêu thứ tự xuất hiện nếu có. `policy_agent.py` áp dụng ánh xạ sau (xem docstring trong file):

| Action bổ sung | Điều kiện kích hoạt |
|---|---|
| `review_seller_handoff` | `primary_issue == late_delivery_seller` |
| `review_carrier_delay` | `primary_issue == late_delivery_logistics` |
| `verify_refund_completion` | `primary_issue` thuộc `{canceled_order_paid, unavailable_order_paid}` (hoàn tiền toàn bộ, cần xác nhận đã hoàn) |
| `coordinate_multi_seller_case` | có secondary issue `multi_seller_order` |
| `verify_payment_allocation` | có secondary issue `split_payment` **và** `primary_issue != valid_split_payment` (loại trừ theo đúng ghi chú của README) |

`confidence` được tính xác định từ mức đầy đủ của dữ liệu (base 0.95, trừ điểm khi rơi vào nhánh fallback, thiếu item, `reconciled=None`, hoặc không xác định được `customer_unique_id`), không lấy từ LLM.

## 5. Chạy thử

```bash
py main.py EC_001     # chạy 1 case để kiểm tra nhanh
py main.py             # chạy toàn bộ 50 case, ghi output/, trace.jsonl, metadata.json
```
