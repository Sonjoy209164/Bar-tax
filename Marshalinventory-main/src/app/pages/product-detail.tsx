import { useNavigate, useParams } from "react-router";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ArrowLeft, Edit, Download, Database, CheckCircle, Clock, User } from "lucide-react";
import { motion } from "motion/react";

const timeline = [
  {
    event: "Product Created",
    time: "2024-03-15 10:30 AM",
    user: "Sarah Chen",
  },
  {
    event: "Stock Updated",
    time: "2024-04-10 14:22 PM",
    user: "Mike Johnson",
  },
  {
    event: "Synced to RAG",
    time: "2024-04-12 09:15 AM",
    user: "System",
  },
  {
    event: "Price Updated",
    time: "2024-04-14 11:45 AM",
    user: "Sarah Chen",
  },
];

export function ProductDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams();

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/inventory")}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="mb-1">Wireless Headphones Pro</h1>
            <p className="text-sm text-muted-foreground">SKU: WHP-001 • Audio</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
          <Button onClick={() => navigate(`/inventory/${id}/edit`)}>
            <Edit className="mr-2 h-4 w-4" />
            Edit
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="lg:col-span-2 space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle>Product Overview</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <img
                    src="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&h=400&fit=crop"
                    alt="Wireless Headphones Pro"
                    className="rounded-lg object-cover w-full h-64"
                  />
                </div>
                <div className="space-y-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Product Name</p>
                    <p className="font-medium">Wireless Headphones Pro</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Category</p>
                    <p className="font-medium">Audio</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Brand</p>
                    <p className="font-medium">AudioTech</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Price</p>
                    <p className="text-2xl font-bold">$299.99</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Stock</p>
                    <div className="flex items-center gap-2">
                      <p className="text-xl font-bold">45</p>
                      <Badge variant="success">In Stock</Badge>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Tabs defaultValue="description">
            <TabsList>
              <TabsTrigger value="description">Description</TabsTrigger>
              <TabsTrigger value="metadata">Metadata</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>
            <TabsContent value="description" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Product Description</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-1">
                      Short Description
                    </p>
                    <p>Premium wireless headphones with noise cancellation</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-1">
                      Full Description
                    </p>
                    <p className="text-muted-foreground leading-relaxed">
                      Experience superior sound quality with our Wireless Headphones Pro. Features
                      active noise cancellation, 30-hour battery life, premium leather cushions,
                      and seamless Bluetooth 5.0 connectivity. Perfect for music lovers and
                      professionals who demand the best audio experience.
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-2">Tags</p>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">electronics</Badge>
                      <Badge variant="secondary">wireless</Badge>
                      <Badge variant="secondary">audio</Badge>
                      <Badge variant="secondary">premium</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="metadata" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Product Metadata</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between border-b border-border pb-3">
                      <span className="text-muted-foreground">Material</span>
                      <span className="font-medium">Aluminum & Leather</span>
                    </div>
                    <div className="flex justify-between border-b border-border pb-3">
                      <span className="text-muted-foreground">Weight</span>
                      <span className="font-medium">250g</span>
                    </div>
                    <div className="flex justify-between border-b border-border pb-3">
                      <span className="text-muted-foreground">Battery Life</span>
                      <span className="font-medium">30 hours</span>
                    </div>
                    <div className="flex justify-between border-b border-border pb-3">
                      <span className="text-muted-foreground">Connectivity</span>
                      <span className="font-medium">Bluetooth 5.0</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Color Options</span>
                      <span className="font-medium">Black, Silver, Navy</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="history" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Product History</CardTitle>
                  <CardDescription>Timeline of all changes and updates</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {timeline.map((item, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.1, duration: 0.3 }}
                        className="flex gap-4"
                      >
                        <div className="flex flex-col items-center">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
                            <Clock className="h-4 w-4 text-primary" />
                          </div>
                          {index < timeline.length - 1 && (
                            <div className="w-px flex-1 bg-border mt-2" />
                          )}
                        </div>
                        <div className="flex-1 pb-4">
                          <p className="font-medium">{item.event}</p>
                          <p className="text-sm text-muted-foreground">{item.time}</p>
                          <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                            <User className="h-3 w-3" />
                            {item.user}
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle>RAG Indexing Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
                  <CheckCircle className="h-6 w-6 text-green-500" />
                </div>
                <div>
                  <p className="font-medium">Indexed</p>
                  <p className="text-sm text-muted-foreground">Last synced 2 hours ago</p>
                </div>
              </div>
              <Button variant="outline" className="w-full">
                <Database className="mr-2 h-4 w-4" />
                Re-sync to RAG
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Export Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button variant="outline" className="w-full justify-start">
                <Download className="mr-2 h-4 w-4" />
                Export as JSON
              </Button>
              <Button variant="outline" className="w-full justify-start">
                <Download className="mr-2 h-4 w-4" />
                Export as DOC
              </Button>
            </CardContent>
          </Card>

          <Card className="border-primary/50 bg-gradient-to-br from-primary/5 to-accent/5">
            <CardHeader>
              <CardTitle>Product Stats</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">AI Queries</span>
                <span className="font-medium">142</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Export Count</span>
                <span className="font-medium">8</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Last Updated</span>
                <span className="font-medium">Today</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
