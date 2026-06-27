import React from 'react';
import { useAuthStore } from '../store/authStore';

/**
 * Full-screen block displayed when the backend returns a 403 with
 * `code: SUBSCRIPTION_EXPIRED`. The sidebar and route content are intentionally
 * NOT rendered while this is up — the user can only either contact support
 * or sign out.
 *
 * The message is shown in Arabic + English together so it works for any
 * tenant regardless of saved language preference.
 */
export const SubscriptionBlockPage: React.FC = () => {
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="fixed inset-0 z-[2000] bg-gradient-to-br from-red-50 via-white to-orange-50 flex items-center justify-center p-6">
      <div className="max-w-[640px] w-full bg-white rounded-2xl shadow-2xl border border-red-200 overflow-hidden">
        {/* Header band */}
        <div className="bg-red-600 text-white px-8 py-6 flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-red-700/40 grid place-items-center text-[28px]">
            ⚠️
          </div>
          <div>
            <div className="text-[12px] font-bold uppercase tracking-widest opacity-90">
              SuperPOS
            </div>
            <div className="text-[20px] font-bold leading-tight mt-0.5">
              Account Suspended · الحساب موقوف
            </div>
          </div>
        </div>

        {/* Bilingual body */}
        <div className="p-8 space-y-6">
          {/* Arabic — RTL forced regardless of current locale */}
          <div dir="rtl" className="text-right">
            <div className="text-[11.5px] uppercase tracking-wider font-bold text-red-600 mb-2">
              العربية
            </div>
            <p className="text-[16px] leading-relaxed text-neutral-800 font-semibold">
              تنبيه عاجل: تم إيقاف الحساب مؤقتاً.
            </p>
            <p className="text-[14px] leading-relaxed text-neutral-600 mt-1">
              يرجى تجديد الاشتراك أو التواصل مع الإدارة لاستعادة الخدمة فوراً.
            </p>
          </div>

          <div className="border-t border-neutral-200" />

          {/* English — LTR */}
          <div dir="ltr" className="text-left">
            <div className="text-[11.5px] uppercase tracking-wider font-bold text-red-600 mb-2">
              English
            </div>
            <p className="text-[16px] leading-relaxed text-neutral-800 font-semibold">
              Account Suspended.
            </p>
            <p className="text-[14px] leading-relaxed text-neutral-600 mt-1">
              Your store account is inactive or your subscription has expired.
              Please contact support to restore access.
            </p>
          </div>

          {/* Actions */}
          <div className="pt-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <a
              href="mailto:support@superpos.io?subject=Subscription%20renewal%20%2F%20Account%20suspended"
              className="flex-1 inline-flex items-center justify-center gap-2 h-12 px-6 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[14px] focus-ring transition"
            >
              📧 Contact support · تواصل مع الدعم
            </a>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center justify-center h-12 px-6 rounded-md border border-neutral-300 text-neutral-700 font-semibold text-[14px] hover:bg-neutral-50 focus-ring transition"
            >
              Sign out · تسجيل الخروج
            </button>
          </div>
        </div>

        {/* Footer note */}
        <div className="px-8 py-3 bg-neutral-50 border-t border-neutral-200 text-[12px] text-neutral-500 text-center">
          All POS, sales and inventory operations are disabled while the account is suspended.
        </div>
      </div>
    </div>
  );
};
