import { Geist, Geist_Mono, Inter, Playfair_Display } from "next/font/google";
import type { Metadata } from "next";
import { Toaster } from "react-hot-toast";
import { Nav } from "@/components/nav";
import { RequireAuth } from "@/components/require-auth";
import { AuthProvider } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";
import "./globals.css";

const playfairDisplayHeading = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-heading",
});

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Argus Dashboard",
  description: "Registration analytics dashboard for Argus",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={cn(
        "dark",
        "h-full",
        "antialiased",
        geistSans.variable,
        geistMono.variable,
        "font-sans",
        inter.variable,
        playfairDisplayHeading.variable,
      )}
    >
      <body className="flex min-h-full flex-col">
        <AuthProvider>
          <Nav />
          <main className="mx-auto w-full max-w-4xl flex-1 p-8">
            <RequireAuth>{children}</RequireAuth>
          </main>
        </AuthProvider>
        <Toaster
          toastOptions={{
            className:
              "!rounded-lg !border !border-border !bg-card !text-sm !text-foreground",
          }}
        />
      </body>
    </html>
  );
}
