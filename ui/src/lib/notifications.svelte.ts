import { createNotice, type Notice, type NoticeInput } from "./notifications";

let items = $state<Notice[]>([]);
const MAX_NOTICES = 50;

export const notifications = {
  get items(): Notice[] {
    return items;
  },
  push(input: NoticeInput): Notice {
    const notice = createNotice(input);
    items = [notice, ...items].slice(0, MAX_NOTICES);
    return notice;
  },
  dismiss(id: string): void {
    items = items.filter((notice) => notice.id !== id);
  },
  clear(): void {
    items = [];
  }
};
