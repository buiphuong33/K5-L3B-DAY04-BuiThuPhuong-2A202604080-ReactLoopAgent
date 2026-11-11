# Ghi chú phân tích · Day 04

Họ và tên: Bùi Thu Phương
MSSV: 2A202604080

Cấu hình cả hai lần chạy: agent `openai / gpt-4o-mini`, judge `openai / gpt-4o-mini`, `max_steps = 8`, dataset `core` (22 case), snapshot mặc định.

## 1. Case được chọn

- **ID case:** H1 (lỗi tương tự xuất hiện ở H6)
- **Câu hỏi H1:** điều tra incident GitHub `h02n9572mx9y`, *theo liên kết do incident cung cấp* để tìm nguyên nhân và ảnh hưởng, rồi đối chiếu với incident Cloudflare `yaa0witbl2me`, dẫn nguồn cho từng bên.
- **Expected:** đọc `h02n9572mx9y`, **rồi đọc incident được dẫn tới `xr3myzj7ms51`**, và đọc Cloudflare `yaa0witbl2me`; không suy ra nguyên nhân chung; dẫn nguồn từng bên; nêu dữ liệu có thể bị cắt.
- **Câu trả lời của agent:** liệt kê tên, trạng thái, thời gian, component của hai incident `h02n9572mx9y` và `yaa0witbl2me`. Agent chỉ *chép* link `https://www.githubstatus.com/incidents/xr3myzj7ms51` vào câu trả lời ("bên cung cấp liên kết tóm tắt") mà không đọc nó, nên không nêu được nguyên nhân/ảnh hưởng thực sự từ incident gộp, và không nói dữ liệu có thể bị cắt.
- **Điểm ở lần chạy 1:** H1 = **60** (judge 65, bị code áp trần 60). H6 = **60** (judge 70, áp trần 60).

## 2. Bằng chứng trong trace

Trace H1 trong `eval_before.json`:

```text
{'event': 'model', 'step': 1, 'finish': 'tool_calls', 'tool_calls': 2}
  step 1 get_incident_details {"provider": "github", "incident_id": "h02n9572mx9y"}   ok=True
  step 1 get_incident_details {"provider": "cloudflare", "incident_id": "yaa0witbl2me"} ok=True
{'event': 'model', 'step': 2, 'finish': 'stop', 'tool_calls': 0}
{'event': 'final', 'step': 2}

grade.mechanical.violations: ['Cần tool calls ở ít nhất 2 model steps khác nhau.']
```

Kết quả tool của `h02n9572mx9y` có update (18:16 UTC 04/11/2026):
"Please refer to the combined summary in the related incident: https://www.githubstatus.com/incidents/xr3myzj7ms51".
Model **đã thấy** link này (có chép nó vào answer) nhưng dừng ngay ở step 2, không gọi `get_incident_details` cho `xr3myzj7ms51`.

H6 có cùng mẫu lỗi: step 1 gọi `get_status` + `get_incident_details(h02n9572mx9y)`, step 2 trả lời luôn và kết luận "báo cáo không chỉ rõ nguyên nhân" trong khi chưa đọc incident gộp.

**Nguyên nhân có thể:**
- Prompt cũ không yêu cầu đi theo incident liên quan; gpt-4o-mini có xu hướng gọi song song các tool "thấy ngay" trong câu hỏi rồi trả lời ở bước kế tiếp, không lập kế hoạch nhiều bước.
- Loop không có cơ chế nào kiểm tra câu trả lời trước khi chấp nhận: hễ `finish == 'stop'` là `completed`.
- Đây là lỗi ở prompt + loop, không phải giới hạn dữ liệu: dữ liệu cần thiết có trong snapshot và tool trả về đầy đủ.

## 3. Thay đổi đã thực hiện

- **Sửa gì, ở đâu** (`agent.py`):
  1. **`SYSTEM_PROMPT`**: thêm quy tắc đi theo incident được dẫn tới trước khi kết luận; dẫn đúng trường `url` của tool cho từng provider, không tự tạo URL; nêu khi `truncated`/`updates_total` cho thấy dữ liệu bị cắt; timeout là "không kiểm tra được"; không suy ra nguyên nhân chung khi nguồn không nói.
  2. **Kiểm tra link chưa đọc (`validation_unfollowed_link`)**: sau mỗi `get_incident_details` thành công, loop quét nội dung update bằng regex `.../incidents/<id>` (githubstatus / cloudflarestatus). Nếu model định trả lời trong khi còn incident được dẫn tới mà chưa gọi, loop ghi event vào trace và thêm một message nhắc model đọc tiếp rồi viết lại. Chỉ nhắc **một lần** mỗi run để không tốn budget; không hard-code ID nào.
  3. **Kiểm tra nguồn (`validation_missing_source`)** theo contract `tests/test_validation.py`: lưu `url` của mọi `get_incident_details` thành công; nếu final answer không chứa URL nào trong số đó thì ghi event, nhắc model sửa trong phạm vi `max_steps`; hết lượt vẫn thiếu thì trả `max_steps`. Không bắt URL khi không có incident thành công.
  4. Dùng `getattr(tools, 'schemas' / 'system_prompt', ...)` để tương thích tools bonus.
- **Vì sao chọn thay đổi này:** H1 và H6 cùng mất điểm vì một hành vi (không theo link), có bằng chứng rõ trong trace và được code chấm bắt (`min_tool_steps`). Chỉ sửa prompt thì gpt-4o-mini vẫn có thể bỏ qua; kiểm tra trong loop là cơ chế xác định, dựa trên dữ liệu tool thật chứ không dựa vào ID của case. Kiểm tra trực tiếp: `_linked_incidents` trên snapshot trả `{('github', 'xr3myzj7ms51')}` cho `h02n9572mx9y`. 37/37 unit tests pass.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 80.45 | 76.27 |
| Điểm case đã chọn (H1 / H6) | 60 / 60 | 60 / 80 |
| Vi phạm kiểm tra bằng code | H1, H6: "cần tool calls ở ≥ 2 model steps" | H2: "chưa gọi tool cần thiết: get_status" |
| Số model calls (agent) | 49 | 53 |
| Token agent (prompt / completion / total) | 31 231 / 9 624 / 40 855 | 49 291 / 11 503 / 60 794 |
| Token judge (total) | 40 900 | 42 594 |
| Chi phí agent ước tính* | ≈ 0,010 USD | ≈ 0,014 USD |

\* Provider không trả chi phí; ước tính theo giá công bố của gpt-4o-mini (0,15 USD / 1M token input, 0,60 USD / 1M token output), chưa tính judge.

Điểm từng case (trước → sau): E1 65→65, E2 75→75, E3 75→75, **E4 100→65**, E5 65→75, **E6 70→95**, A1 75→75, **A2 100→75**, **A3 75→90**, A4 100→100, **A5 60→35**, A6 80→75, A7 75→75, A8 80→85, H1 60→60, **H2 100→50**, H3 95→95, **H4 100→80**, H5 100→95, **H6 60→80**, H7 80→80, H8 80→78.

- **Lỗi đã giải quyết:** H1 và H6 không còn dừng sớm. Trace sau có event `validation_unfollowed_link` (pending `github:xr3myzj7ms51`), sau đó agent gọi `get_incident_details(github, xr3myzj7ms51)` ở step 3, vi phạm `min_tool_steps` biến mất. H6 tăng 60 → 80. H1 vẫn 60: judge giờ trừ điểm vì chưa trả lời rõ "có bằng chứng chung nguyên nhân không", tức hành vi điều tra đã đúng nhưng phần kết luận chưa đủ rõ.
- **Lỗi mới xuất hiện:** H2 (100 → 50). Lần 2 agent chỉ gọi `get_incident_details(t89g2q1800fr)`, không gọi `get_status`, nên không xác nhận được trạng thái hiện tại của Actions và bị code áp trần 50 (judge 85). Có thể prompt mới nhấn mạnh việc đọc incident làm model bỏ bước kiểm tra status, hoặc chỉ do ngẫu nhiên; một lần chạy không phân biệt được. Hướng sửa: thêm quy tắc "khi câu hỏi nói về trạng thái *hiện tại*, luôn gọi `get_status` trước".
- **Lỗi còn lại:** A5 (60 → 35). Cả hai lần agent đều khẳng định "không có incident nào trong 2025" dù tool chỉ xem 50 incident gần nhất; judge lần 2 chấm khắt hơn. Cải tiến không nhắm vào lỗi này. Hướng sửa: quy tắc prompt rằng khoảng thời gian nằm ngoài dữ liệu thì phải nói "không đủ dữ liệu", không kết luận "không có".
- **Dao động của judge:** E4, A2, H4 giảm 20–35 điểm với cùng tool và nội dung gần như giống hệt (H4 chỉ là bài thơ, không dùng tool). E6, A3 tăng 15–25 điểm dù loop không can thiệp. `validation_unfollowed_link` chỉ kích hoạt ở H1/H6, nên ở 20 case còn lại khác biệt chỉ đến từ system prompt dài hơn và tính ngẫu nhiên. Điểm tổng giảm 4,18 chủ yếu do nhiễu judge và lỗi H2, không cho thấy cải tiến làm agent kém đi; ngược lại cũng không đủ chứng minh nó làm tốt hơn trên toàn bộ.
- **Chi phí:** token agent tăng ~49% do system prompt dài hơn được gửi ở mọi model call và H1/H6 thêm bước với context lớn.

## 5. Giới hạn

- **Điểm judge:** judge là LLM (gpt-4o-mini), cùng model với agent nên có thể thiên lệch khi tự chấm; điểm dao động giữa các lần chạy và lý do judge đôi khi mâu thuẫn với điểm (ví dụ A2 được 100 nhưng reason vẫn nêu thiếu sót). Cần đối chiếu `expected` và trace thay vì tin điểm tuyệt đối.
- **Snapshot:** dữ liệu được lưu ngày 09/11/2026 và tool chỉ xem 50 incident gần nhất, mỗi incident giữ tối đa 3 update (900 ký tự/update); kết quả không phản ánh trạng thái thực tế hiện tại và có thể thiếu thông tin bị cắt.
- **Một lần chạy mỗi phiên bản:** chênh lệch điểm trước/sau có thể một phần do ngẫu nhiên của model và judge; cần chạy nhiều lần để kết luận chắc chắn.
- **Giới hạn của cải tiến:** kiểm tra nguồn chỉ xác nhận *có mặt* một URL đã quan sát, không chứng minh mọi claim đều có nguồn; nhắc theo link chỉ chạy một lần và chỉ nhận dạng link dạng `githubstatus.com/cloudflarestatus.com/incidents/<id>`; mỗi lần nhắc tốn thêm một model call.
