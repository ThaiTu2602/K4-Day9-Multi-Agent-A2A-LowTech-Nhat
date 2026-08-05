# Multi-Agent Architecture & Handoff Flow

Hệ thống điều tra khiếu nại thương mại điện tử (Olist Dispute Resolution) được thiết kế theo kiến trúc **Heterogeneous Multi-Agent** chuyên biệt hóa vai trò, kết hợp mô hình suy luận LLM cho các Agent quyết định và kiểm chứng độc lập.

## 1. Sơ đồ Kiến trúc & Luồng Handoff

```mermaid
flowchart TD
    Input[Input Case EC_xxx.json] --> Coord[Coordinator Agent]
    
    subgraph Data Retrieval Agents
        Customer[Customer Agent]
        OrderProduct[Order & Product Agent]
        Delivery[Delivery Agent]
        Payment[Payment Agent]
    end

    subgraph LLM Decision & Verification Agents
        Policy[Policy Agent - llama-3.1-8b-instant]
        Verifier[Verifier Agent - llama-3.1-8b-instant]
    end

    Coord -->|1. Customer ID| Customer
    Customer -->|Handoff 1: Unique Customer ID & Related Order IDs| Coord
    
    Coord -->|2. Claimed Order ID| OrderProduct
    OrderProduct -->|Handoff 2: Items, Products & Raw Categories| Coord

    Coord -->|3. Order Timestamps & Items| Delivery
    Delivery -->|Handoff 3: Delivery & Handoff Variance Hours| Coord
    
    Coord -->|4. Items & Payment Rows| Payment
    Payment -->|Handoff 4: Total Reconciliation & Variance| Coord
    
    Coord -->|5. Combined Evidence & Context| Policy
    Policy -->|Handoff 5: Primary/Secondary Issues, Refund & Actions| Coord
    
    Coord -->|6. Output Draft Object| Verifier
    Verifier -->|Handoff 6: Verified Output & Audited Confidence| Coord
    
    Coord --> Trace[trace.jsonl]
    Coord --> Output[Output EC_xxx.json]
```

## 2. Vai trò, Mô hình & Quyền truy cập dữ liệu của từng Agent

| Agent | Mô hình LLM | Vai trò chính | Dữ liệu truy cập (Data Scope) | Handoff Output |
| :--- | :--- | :--- | :--- | :--- |
| **Coordinator Agent** | Rule Engine | Nhận case, điều phối luồng 6 bước handoff, thu thập bằng chứng và ghi vết `trace.jsonl`. | `input/EC_xxx.json`, `output/` | Trái tim điều phối hệ thống. |
| **Customer Agent** | Data Engine | Truy vết danh tính khách hàng & kiểm tra lịch sử đơn hàng trước đây. | `olist_customers_dataset.csv`, `olist_orders_dataset.csv` | `customer_unique_id`, `related_order_ids`, `is_repeat_customer`. |
| **Order & Product Agent** | Data Engine | Truy xuất item, sản phẩm và danh mục `product_category_name` chuẩn gốc từ CSV. | `olist_order_items_dataset.csv`, `olist_products_dataset.csv` | `items`, `product_ids`, `category_names`. |
| **Delivery Agent** | Math Engine | Tính toán chênh lệch giao hàng (`delivery_variance_hours`) và từng seller bàn giao (`handoff_variance_hours`). | `olist_orders_dataset.csv`, `olist_order_items_dataset.csv` | `delivered_at`, `estimated_delivery_at`, `seller_handoff_analysis`, `late_handoff_seller_ids`. |
| **Payment Agent** | Math Engine | Tính tổng giá trị đơn, tổng tiền ship, tổng thanh toán và kiểm tra đối soát (`reconciled`). | `olist_order_items_dataset.csv`, `olist_order_payments_dataset.csv` | `item_total_brl`, `freight_total_brl`, `expected_total_brl`, `difference_brl`, `reconciled`. |
| **Policy Agent** | `llama-3.1-8b-instant` (8B) | Áp dụng chính xác bảng quy tắc `EC_POLICY_V2` + Gọi LLM lập luận lý do khiếu nại. | Handoff Results từ Customer, OrderProduct, Delivery, Payment | `primary_issue`, `secondary_issues`, `cause_code`, `responsible_parties`, `refund`, `actions`. |
| **Verifier Agent** | `llama-3.1-8b-instant` (8B) | Kiểm tra độc lập Schema JSON, cắt giới hạn độ dài mảng, gọi LLM audit `confidence`. | Output JSON draft từ Policy Agent | Output JSON hoàn chỉnh chuẩn hóa. |

## 3. Quy trình Kiểm chứng & Đảm bảo Chất lượng (Verification & Safety)

1. **Tuân thủ quy chế tham số mô hình**: Các Agent quyết định dùng mô hình **Groq `llama-3.1-8b-instant` (8B parameters $\le$ 10B)**.
2. **Khả năng kiểm chứng bằng chứng (Verifiable Evidence)**: Tất cả Evidence ID (`order:...`, `item:...`, `payment:...`, `seller:...`, `policy:...`) được khởi tạo chuẩn xác 100% từ dữ liệu thực tế.
3. **Không ảo tưởng sự kiện (Hallucination Prevention)**: Dữ liệu định lượng (thời gian, tiền bạc) được xử lý bằng Deterministic Engine trước khi truyền sang LLM.
