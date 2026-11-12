import Link from "next/link";
import { ShieldIcon, ArrowRightIcon } from "@/components/ui/Icons";
import { Button } from "@/components/ui/Button";

export default function DemoPage() {
  return (
    <main className="min-h-screen bg-[#090D10] text-[#F1F5F4] flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md p-8 rounded-xl bg-[#11181D] border border-[#1E2B27] shadow-2xl text-center space-y-6">
        <div className="w-12 h-12 rounded-xl bg-[#151F24] border border-[#1E2B27] flex items-center justify-center text-[#16E6A0] mx-auto">
          <ShieldIcon className="w-6 h-6" />
        </div>

        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-[#16E6A0] bg-[#16E6A0]/10 px-2 py-0.5 rounded border border-[#16E6A0]/20">
            Seatbelt Control Plane
          </span>
          <h1 className="text-xl font-bold tracking-tight text-[#F1F5F4] mt-3">
            Open Governance Console
          </h1>
          <p className="text-xs text-[#91A09D] mt-2 leading-relaxed">
            Access the live governance dashboard to inspect evaluated transactions, manage agent mandate authorizations, and test policy enforcement rules.
          </p>
        </div>

        <div className="pt-2 space-y-3">
          <Link href="/dashboard" className="block w-full">
            <Button size="lg" className="w-full" icon={<ArrowRightIcon className="w-4 h-4 ml-1 order-last" />}>
              Launch Dashboard
            </Button>
          </Link>
          <Link href="/" className="inline-block text-xs text-[#91A09D] hover:text-[#F1F5F4] transition-colors">
            ← Return to public website
          </Link>
        </div>
      </div>
    </main>
  );
}
