import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { ArrowLeft, Upload, Save, X } from "lucide-react";
import { motion } from "motion/react";

export function ProductFormPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const [includeInRAG, setIncludeInRAG] = useState(true);
  const [exportJSON, setExportJSON] = useState(true);
  const [exportDOC, setExportDOC] = useState(false);
  const [tags, setTags] = useState<string[]>(["electronics", "wireless"]);
  const [newTag, setNewTag] = useState("");

  const addTag = () => {
    if (newTag && !tags.includes(newTag)) {
      setTags([...tags, newTag]);
      setNewTag("");
    }
  };

  const removeTag = (tag: string) => {
    setTags(tags.filter((t) => t !== tag));
  };

  const handleSave = () => {
    navigate("/inventory");
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate("/inventory")}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="mb-1">{isEdit ? "Edit Product" : "Add New Product"}</h1>
          <p className="text-muted-foreground">
            {isEdit ? "Update product information" : "Create a new product in your inventory"}
          </p>
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
              <CardTitle>Basic Information</CardTitle>
              <CardDescription>Core product details and identification</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="name">Product Name</Label>
                  <Input id="name" placeholder="Enter product name" defaultValue={isEdit ? "Wireless Headphones Pro" : ""} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sku">SKU</Label>
                  <Input id="sku" placeholder="e.g., WHP-001" defaultValue={isEdit ? "WHP-001" : ""} />
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="category">Category</Label>
                  <Select defaultValue={isEdit ? "audio" : undefined}>
                    <SelectTrigger id="category">
                      <SelectValue placeholder="Select category" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="audio">Audio</SelectItem>
                      <SelectItem value="electronics">Electronics</SelectItem>
                      <SelectItem value="accessories">Accessories</SelectItem>
                      <SelectItem value="footwear">Footwear</SelectItem>
                      <SelectItem value="office">Office</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="brand">Brand</Label>
                  <Input id="brand" placeholder="Enter brand name" defaultValue={isEdit ? "AudioTech" : ""} />
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="stock">Stock Quantity</Label>
                  <Input id="stock" type="number" placeholder="0" defaultValue={isEdit ? "45" : ""} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="price">Price (USD)</Label>
                  <Input id="price" type="number" step="0.01" placeholder="0.00" defaultValue={isEdit ? "299.99" : ""} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Product Description</CardTitle>
              <CardDescription>Detailed product information for customers and AI</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="short-description">Short Description</Label>
                <Input
                  id="short-description"
                  placeholder="Brief one-line description"
                  defaultValue={isEdit ? "Premium wireless headphones with noise cancellation" : ""}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="full-description">Full Description</Label>
                <Textarea
                  id="full-description"
                  placeholder="Detailed product description, features, specifications..."
                  rows={6}
                  defaultValue={
                    isEdit
                      ? "Experience superior sound quality with our Wireless Headphones Pro. Features active noise cancellation, 30-hour battery life, premium leather cushions, and seamless Bluetooth 5.0 connectivity. Perfect for music lovers and professionals."
                      : ""
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="tags">Tags</Label>
                <div className="flex gap-2">
                  <Input
                    id="tags"
                    placeholder="Add tag..."
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
                  />
                  <Button type="button" onClick={addTag}>Add</Button>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {tags.map((tag) => (
                    <div
                      key={tag}
                      className="flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-sm"
                    >
                      {tag}
                      <button
                        onClick={() => removeTag(tag)}
                        className="ml-1 text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Product Image</CardTitle>
              <CardDescription>Upload product photos</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center rounded-lg border-2 border-dashed border-border p-12 transition-colors hover:border-primary">
                <div className="text-center">
                  <Upload className="mx-auto h-12 w-12 text-muted-foreground" />
                  <div className="mt-4">
                    <Button variant="outline">Choose Files</Button>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    PNG, JPG, WebP up to 10MB
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle>Export & AI Settings</CardTitle>
              <CardDescription>Configure data export and AI features</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="rag">Include in RAG</Label>
                  <p className="text-xs text-muted-foreground">
                    Make searchable via AI assistant
                  </p>
                </div>
                <Switch id="rag" checked={includeInRAG} onCheckedChange={setIncludeInRAG} />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="json">Export as JSON</Label>
                  <p className="text-xs text-muted-foreground">
                    Include in JSON exports
                  </p>
                </div>
                <Switch id="json" checked={exportJSON} onCheckedChange={setExportJSON} />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="doc">Export as DOC</Label>
                  <p className="text-xs text-muted-foreground">
                    Include in document exports
                  </p>
                </div>
                <Switch id="doc" checked={exportDOC} onCheckedChange={setExportDOC} />
              </div>
            </CardContent>
          </Card>

          <Card className="border-primary/50 bg-gradient-to-br from-primary/5 to-accent/5">
            <CardHeader>
              <CardTitle>Custom Metadata</CardTitle>
              <CardDescription>Additional product attributes</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="meta-key">Attribute Name</Label>
                <Input id="meta-key" placeholder="e.g., Material" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="meta-value">Value</Label>
                <Input id="meta-value" placeholder="e.g., Aluminum" />
              </div>
              <Button variant="outline" className="w-full">
                Add Attribute
              </Button>
            </CardContent>
          </Card>

          <div className="sticky top-6 space-y-3">
            <Button onClick={handleSave} className="w-full" size="lg">
              <Save className="mr-2 h-4 w-4" />
              {isEdit ? "Update Product" : "Create Product"}
            </Button>
            <Button variant="outline" className="w-full" onClick={() => navigate("/inventory")}>
              Cancel
            </Button>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
