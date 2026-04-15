import { useState } from "react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Send, Sparkles, Package, ExternalLink } from "lucide-react";
import { motion } from "motion/react";

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  products?: Array<{ name: string; sku: string; price: string; stock: number }>;
};

const suggestedPrompts = [
  "Show me all products with low stock",
  "What are the most expensive items in Electronics?",
  "Find wireless headphones under $300",
  "Which products were updated this week?",
];

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "assistant",
      content:
        "Hello! I'm your AI inventory assistant. I can help you search products, check stock levels, find specific items, and answer questions about your catalog. What would you like to know?",
      timestamp: "10:00 AM",
    },
  ]);
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: messages.length + 1,
      role: "user",
      content: input,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages([...messages, userMessage]);

    setTimeout(() => {
      const assistantMessage: Message = {
        id: messages.length + 2,
        role: "assistant",
        content:
          "I found 3 wireless headphones under $300 in your inventory. Here are the products:",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        products: [
          { name: "Wireless Headphones Pro", sku: "WHP-001", price: "$299.99", stock: 45 },
          { name: "Budget Wireless Earbuds", sku: "BWE-102", price: "$79.99", stock: 128 },
          { name: "Sport Wireless Headset", sku: "SWH-203", price: "$149.99", stock: 67 },
        ],
      };
      setMessages((prev) => [...prev, assistantMessage]);
    }, 1000);

    setInput("");
  };

  const handlePromptClick = (prompt: string) => {
    setInput(prompt);
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-6 p-6">
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.4 }}
        className="w-80 space-y-4"
      >
        <Card>
          <CardContent className="p-6">
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              <h3 className="font-semibold">AI Assistant</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              Powered by RAG technology to answer questions about your entire product catalog
              instantly.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <h4 className="mb-3 text-sm font-semibold">Suggested Prompts</h4>
            <div className="space-y-2">
              {suggestedPrompts.map((prompt, index) => (
                <motion.button
                  key={index}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.1, duration: 0.3 }}
                  onClick={() => handlePromptClick(prompt)}
                  className="w-full rounded-lg border border-border bg-background p-3 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {prompt}
                </motion.button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-primary/50 bg-gradient-to-br from-primary/5 to-accent/5">
          <CardContent className="p-6">
            <h4 className="mb-2 text-sm font-semibold">Indexed Products</h4>
            <p className="text-3xl font-bold">1,248</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Last updated 2 hours ago
            </p>
          </CardContent>
        </Card>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.4 }}
        className="flex flex-1 flex-col rounded-xl border border-border bg-card"
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary">
              <Sparkles className="h-4 w-4 text-primary-foreground" />
            </div>
            <div>
              <h3 className="font-semibold">Product Assistant</h3>
              <div className="flex items-center gap-1">
                <div className="h-2 w-2 rounded-full bg-green-500" />
                <span className="text-xs text-muted-foreground">Online</span>
              </div>
            </div>
          </div>
          <Button variant="outline" size="sm">
            Clear History
          </Button>
        </div>

        <ScrollArea className="flex-1 p-6">
          <div className="space-y-6">
            {messages.map((message, index) => (
              <motion.div
                key={message.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                className={`flex gap-4 ${message.role === "user" ? "justify-end" : ""}`}
              >
                {message.role === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
                    <Sparkles className="h-4 w-4 text-primary-foreground" />
                  </div>
                )}
                <div
                  className={`max-w-2xl space-y-3 ${
                    message.role === "user" ? "flex flex-col items-end" : ""
                  }`}
                >
                  <div
                    className={`rounded-2xl px-4 py-3 ${
                      message.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted"
                    }`}
                  >
                    <p className="text-sm leading-relaxed">{message.content}</p>
                  </div>
                  {message.products && (
                    <div className="space-y-2">
                      {message.products.map((product, idx) => (
                        <Card key={idx} className="transition-shadow hover:shadow-md">
                          <CardContent className="flex items-center justify-between p-4">
                            <div className="flex items-center gap-3">
                              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                                <Package className="h-6 w-6 text-primary" />
                              </div>
                              <div>
                                <p className="font-medium">{product.name}</p>
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                  <span>{product.sku}</span>
                                  <span>•</span>
                                  <span>Stock: {product.stock}</span>
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-4">
                              <span className="text-lg font-bold">{product.price}</span>
                              <Button variant="ghost" size="icon">
                                <ExternalLink className="h-4 w-4" />
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                  <span className="text-xs text-muted-foreground">{message.timestamp}</span>
                </div>
                {message.role === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent">
                    <span className="text-sm font-medium">SC</span>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </ScrollArea>

        <div className="border-t border-border p-4">
          <div className="flex gap-2">
            <Input
              placeholder="Ask about your products..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSend()}
              className="flex-1"
            />
            <Button onClick={handleSend} size="icon">
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Powered by RAG • All answers are based on your product catalog
          </p>
        </div>
      </motion.div>
    </div>
  );
}
