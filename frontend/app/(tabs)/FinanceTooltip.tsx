import React, { useState, useEffect, createContext, useContext } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  ScrollView,
  StyleSheet,
  Dimensions,
  TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// ==================== GLOSSARY CONTEXT ====================
// Load glossary once, share across all tooltips

interface GlossaryEntry {
  term: string;
  short: string;
  detailed: string;
  example: string;
  category: string;
}

interface GlossaryContextType {
  glossary: Record<string, GlossaryEntry>;
  loaded: boolean;
}

const GlossaryContext = createContext<GlossaryContextType>({ glossary: {}, loaded: false });

export function GlossaryProvider({ children }: { children: React.ReactNode }) {
  const [glossary, setGlossary] = useState<Record<string, GlossaryEntry>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchGlossary();
  }, []);

  const fetchGlossary = async () => {
    try {
      const response = await fetch(`${API_URL}/api/glossary`);
      const data = await response.json();
      setGlossary(data.terms || {});
      setLoaded(true);
    } catch (error) {
      console.error('Error fetching glossary:', error);
      // Use built-in fallback if API fails
      setGlossary(FALLBACK_GLOSSARY);
      setLoaded(true);
    }
  };

  return (
    <GlossaryContext.Provider value={{ glossary, loaded }}>
      {children}
    </GlossaryContext.Provider>
  );
}

// ==================== INLINE TOOLTIP COMPONENT ====================
// Wraps a financial term with a tappable info indicator

interface TermTooltipProps {
  termKey: string;          // Key from glossary (e.g., "rsi", "stop_loss")
  displayText?: string;     // What to show inline (defaults to glossary term name)
  style?: any;              // Additional text styles
  children?: React.ReactNode;
}

export function TermTooltip({ termKey, displayText, style, children }: TermTooltipProps) {
  const { glossary } = useContext(GlossaryContext);
  const [showModal, setShowModal] = useState(false);

  const entry = glossary[termKey];
  if (!entry) {
    // If term not in glossary, just render the text normally
    return <Text style={style}>{displayText || children}</Text>;
  }

  return (
    <>
      <TouchableOpacity
        onPress={() => setShowModal(true)}
        style={styles.tooltipTouchable}
        activeOpacity={0.7}
      >
        <Text style={[styles.tooltipText, style]}>
          {displayText || entry.term}
        </Text>
        <Ionicons name="help-circle-outline" size={14} color="#f59e0b" style={styles.tooltipIcon} />
      </TouchableOpacity>

      <Modal
        visible={showModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowModal(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowModal(false)}
        >
          <View style={styles.modalContent}>
            {/* Header */}
            <View style={styles.modalHeader}>
              <View style={styles.modalDragBar} />
            </View>

            <ScrollView style={styles.modalScroll} showsVerticalScrollIndicator={false}>
              {/* Term Title */}
              <Text style={styles.modalTermTitle}>{entry.term}</Text>
              
              {/* Category Badge */}
              <View style={styles.categoryBadge}>
                <Text style={styles.categoryBadgeText}>
                  {getCategoryLabel(entry.category)}
                </Text>
              </View>

              {/* Simple Explanation */}
              <View style={styles.explanationSection}>
                <View style={styles.sectionHeader}>
                  <Ionicons name="bulb-outline" size={18} color="#f59e0b" />
                  <Text style={styles.sectionTitle}>In Simple Words</Text>
                </View>
                <Text style={styles.simpleText}>{entry.short}</Text>
              </View>

              {/* Detailed Explanation */}
              <View style={styles.explanationSection}>
                <View style={styles.sectionHeader}>
                  <Ionicons name="book-outline" size={18} color="#6366f1" />
                  <Text style={styles.sectionTitle}>Detailed Explanation</Text>
                </View>
                <Text style={styles.detailedText}>{entry.detailed}</Text>
              </View>

              {/* Example */}
              {entry.example && (
                <View style={styles.exampleSection}>
                  <View style={styles.sectionHeader}>
                    <Ionicons name="flask-outline" size={18} color="#10b981" />
                    <Text style={styles.sectionTitle}>Real Example</Text>
                  </View>
                  <Text style={styles.exampleText}>{entry.example}</Text>
                </View>
              )}

              {/* Close Button */}
              <TouchableOpacity
                style={styles.closeButton}
                onPress={() => setShowModal(false)}
              >
                <Text style={styles.closeButtonText}>Got it!</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  );
}

// ==================== INFO BUTTON COMPONENT ====================
// Small "?" button that can be placed next to any label

interface InfoButtonProps {
  termKey: string;
  size?: number;
  color?: string;
}

export function InfoButton({ termKey, size = 16, color = '#f59e0b' }: InfoButtonProps) {
  const { glossary } = useContext(GlossaryContext);
  const [showModal, setShowModal] = useState(false);

  const entry = glossary[termKey];
  if (!entry) return null;

  return (
    <>
      <TouchableOpacity
        onPress={() => setShowModal(true)}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        style={styles.infoButton}
      >
        <Ionicons name="help-circle" size={size} color={color} />
      </TouchableOpacity>

      <Modal
        visible={showModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowModal(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowModal(false)}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <View style={styles.modalDragBar} />
            </View>
            <ScrollView style={styles.modalScroll} showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTermTitle}>{entry.term}</Text>
              <View style={styles.categoryBadge}>
                <Text style={styles.categoryBadgeText}>{getCategoryLabel(entry.category)}</Text>
              </View>
              <View style={styles.explanationSection}>
                <View style={styles.sectionHeader}>
                  <Ionicons name="bulb-outline" size={18} color="#f59e0b" />
                  <Text style={styles.sectionTitle}>In Simple Words</Text>
                </View>
                <Text style={styles.simpleText}>{entry.short}</Text>
              </View>
              <View style={styles.explanationSection}>
                <View style={styles.sectionHeader}>
                  <Ionicons name="book-outline" size={18} color="#6366f1" />
                  <Text style={styles.sectionTitle}>Detailed Explanation</Text>
                </View>
                <Text style={styles.detailedText}>{entry.detailed}</Text>
              </View>
              {entry.example && (
                <View style={styles.exampleSection}>
                  <View style={styles.sectionHeader}>
                    <Ionicons name="flask-outline" size={18} color="#10b981" />
                    <Text style={styles.sectionTitle}>Real Example</Text>
                  </View>
                  <Text style={styles.exampleText}>{entry.example}</Text>
                </View>
              )}
              <TouchableOpacity style={styles.closeButton} onPress={() => setShowModal(false)}>
                <Text style={styles.closeButtonText}>Got it!</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  );
}

// ==================== FULL GLOSSARY SCREEN COMPONENT ====================
// A dedicated screen/modal showing all terms organized by category

interface GlossaryScreenProps {
  visible: boolean;
  onClose: () => void;
}

export function GlossaryScreen({ visible, onClose }: GlossaryScreenProps) {
  const { glossary } = useContext(GlossaryContext);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedTerm, setExpandedTerm] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const categories = [
    { key: 'basics', label: 'Basics', icon: 'school-outline' as const, color: '#3b82f6' },
    { key: 'technical', label: 'Charts', icon: 'analytics-outline' as const, color: '#f59e0b' },
    { key: 'trading', label: 'Trading', icon: 'swap-horizontal-outline' as const, color: '#10b981' },
    { key: 'concepts', label: 'Concepts', icon: 'bulb-outline' as const, color: '#8b5cf6' },
    { key: 'tax', label: 'Tax (India)', icon: 'receipt-outline' as const, color: '#ef4444' },
    { key: 'app', label: 'App Terms', icon: 'phone-portrait-outline' as const, color: '#6366f1' },
  ];

  const filteredTerms = Object.entries(glossary).filter(([key, entry]) => {
    const matchesSearch = !searchQuery || 
      entry.term.toLowerCase().includes(searchQuery.toLowerCase()) ||
      entry.short.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = !activeCategory || entry.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.glossaryContainer}>
        {/* Header */}
        <View style={styles.glossaryHeader}>
          <TouchableOpacity onPress={onClose} style={styles.glossaryBackButton}>
            <Ionicons name="close" size={24} color="#fff" />
          </TouchableOpacity>
          <View>
            <Text style={styles.glossaryTitle}>Finance Dictionary</Text>
            <Text style={styles.glossarySubtitle}>Every term explained simply</Text>
          </View>
          <View style={{ width: 40 }} />
        </View>

        {/* Search */}
        <View style={styles.glossarySearchContainer}>
          <View style={styles.glossarySearchBox}>
            <Ionicons name="search" size={20} color="#6b7280" />
            <TextInput
              style={styles.glossarySearchInput}
              placeholder="Search terms..."
              placeholderTextColor="#6b7280"
              value={searchQuery}
              onChangeText={setSearchQuery}
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => setSearchQuery('')}>
                <Ionicons name="close-circle" size={20} color="#6b7280" />
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Category Filters */}
        <ScrollView 
          horizontal 
          showsHorizontalScrollIndicator={false}
          style={styles.categoryScrollContainer}
          contentContainerStyle={styles.categoryScrollContent}
        >
          <TouchableOpacity
            style={[styles.categoryChip, !activeCategory && styles.categoryChipActive]}
            onPress={() => setActiveCategory(null)}
          >
            <Text style={[styles.categoryChipText, !activeCategory && styles.categoryChipTextActive]}>
              All
            </Text>
          </TouchableOpacity>
          {categories.map(cat => (
            <TouchableOpacity
              key={cat.key}
              style={[
                styles.categoryChip,
                activeCategory === cat.key && { backgroundColor: cat.color + '30' }
              ]}
              onPress={() => setActiveCategory(activeCategory === cat.key ? null : cat.key)}
            >
              <Ionicons name={cat.icon} size={14} color={activeCategory === cat.key ? cat.color : '#9ca3af'} />
              <Text style={[
                styles.categoryChipText,
                activeCategory === cat.key && { color: cat.color }
              ]}>
                {cat.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Terms List */}
        <ScrollView style={styles.termsList} contentContainerStyle={styles.termsListContent}>
          {filteredTerms.length === 0 ? (
            <View style={styles.emptySearch}>
              <Ionicons name="search-outline" size={48} color="#6b7280" />
              <Text style={styles.emptySearchText}>No terms found for "{searchQuery}"</Text>
            </View>
          ) : (
            filteredTerms.map(([key, entry]) => {
              const isExpanded = expandedTerm === key;
              const catColor = categories.find(c => c.key === entry.category)?.color || '#6b7280';

              return (
                <TouchableOpacity
                  key={key}
                  style={styles.termCard}
                  onPress={() => setExpandedTerm(isExpanded ? null : key)}
                  activeOpacity={0.8}
                >
                  <View style={styles.termCardHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.termCardTitle}>{entry.term}</Text>
                      <Text style={styles.termCardShort}>{entry.short}</Text>
                    </View>
                    <View style={[styles.termCategoryDot, { backgroundColor: catColor }]} />
                  </View>

                  {isExpanded && (
                    <View style={styles.termCardExpanded}>
                      <View style={styles.termDivider} />
                      
                      <Text style={styles.termDetailedLabel}>Full Explanation:</Text>
                      <Text style={styles.termDetailedText}>{entry.detailed}</Text>
                      
                      {entry.example && (
                        <>
                          <View style={styles.termExampleBox}>
                            <Ionicons name="flash" size={14} color="#10b981" />
                            <Text style={styles.termExampleLabel}> Example:</Text>
                          </View>
                          <Text style={styles.termExampleText}>{entry.example}</Text>
                        </>
                      )}
                    </View>
                  )}

                  <View style={styles.termExpandIndicator}>
                    <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color="#6b7280" />
                  </View>
                </TouchableOpacity>
              );
            })
          )}

          {/* Bottom padding */}
          <View style={{ height: 40 }} />
        </ScrollView>
      </View>
    </Modal>
  );
}

// ==================== HELPER ====================

function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    basics: 'Market Basics',
    technical: 'Chart Indicator',
    trading: 'Trading Term',
    concepts: 'Market Concept',
    tax: 'Indian Tax Rule',
    app: 'App Term',
  };
  return labels[category] || category;
}

// ==================== FALLBACK GLOSSARY ====================
// Used if the API is unreachable

const FALLBACK_GLOSSARY: Record<string, GlossaryEntry> = {
  rsi: {
    term: "RSI",
    short: "A score from 0-100 that tells you if something is 'too expensive' (above 70) or 'on sale' (below 30).",
    detailed: "RSI measures how fast the price has been going up or down. Below 30 means it might bounce up. Above 70 means it might come down. Between 30-70 is normal.",
    example: "If Bitcoin RSI is 72, it means BTC has been going up fast. Some traders see this as a warning to wait for a dip.",
    category: "technical"
  },
  stop_loss: {
    term: "Stop Loss",
    short: "An automatic sell order that protects you from losing too much money on a trade.",
    detailed: "You set it below your buy price. If the price drops to that level, your position is sold automatically to prevent bigger losses.",
    example: "Buy at ₹1,000. Stop loss at ₹930. Worst case: you lose ₹70 per unit instead of potentially much more.",
    category: "trading"
  },
  vda_tax: {
    term: "30% Crypto Tax",
    short: "India charges 30% flat tax on all crypto profits. No deductions allowed.",
    detailed: "All crypto gains are taxed at 30%. You cannot offset losses. 1% TDS is deducted on every transaction above ₹10,000.",
    example: "Profit of ₹1L on Bitcoin? Tax = ₹30,000. Even if you lost ₹80K on Ethereum, tax stays ₹30K.",
    category: "tax"
  }
};

// ==================== STYLES ====================

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const styles = StyleSheet.create({
  // Inline tooltip
  tooltipTouchable: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  tooltipText: {
    textDecorationLine: 'underline',
    textDecorationStyle: 'dotted',
    textDecorationColor: '#f59e0b',
  },
  tooltipIcon: {
    marginLeft: 3,
    opacity: 0.7,
  },

  // Info button
  infoButton: {
    marginLeft: 4,
    opacity: 0.8,
  },

  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1a1a2e',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '80%',
    paddingBottom: 30,
  },
  modalHeader: {
    alignItems: 'center',
    paddingTop: 12,
    paddingBottom: 8,
  },
  modalDragBar: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#4b5563',
  },
  modalScroll: {
    paddingHorizontal: 24,
  },
  modalTermTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 8,
  },
  categoryBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#f59e0b20',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 20,
  },
  categoryBadgeText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '600',
  },
  explanationSection: {
    marginBottom: 20,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  sectionTitle: {
    color: '#9ca3af',
    fontSize: 13,
    fontWeight: '600',
    marginLeft: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  simpleText: {
    color: '#fff',
    fontSize: 17,
    lineHeight: 26,
    fontWeight: '500',
  },
  detailedText: {
    color: '#d1d5db',
    fontSize: 15,
    lineHeight: 24,
  },
  exampleSection: {
    backgroundColor: '#10b98110',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderLeftWidth: 3,
    borderLeftColor: '#10b981',
  },
  exampleText: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
  },
  closeButton: {
    backgroundColor: '#f59e0b',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 10,
  },
  closeButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },

  // Glossary Screen
  glossaryContainer: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  glossaryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 16,
    backgroundColor: '#1a1a2e',
  },
  glossaryBackButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#2d2d44',
    justifyContent: 'center',
    alignItems: 'center',
  },
  glossaryTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#fff',
    textAlign: 'center',
  },
  glossarySubtitle: {
    fontSize: 13,
    color: '#9ca3af',
    textAlign: 'center',
    marginTop: 2,
  },
  glossarySearchContainer: {
    paddingHorizontal: 20,
    paddingVertical: 12,
    backgroundColor: '#1a1a2e',
  },
  glossarySearchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 44,
  },
  glossarySearchInput: {
    flex: 1,
    color: '#fff',
    fontSize: 15,
    marginLeft: 10,
  },
  categoryScrollContainer: {
    maxHeight: 48,
    backgroundColor: '#1a1a2e',
    paddingBottom: 12,
  },
  categoryScrollContent: {
    paddingHorizontal: 16,
    gap: 8,
    flexDirection: 'row',
  },
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: '#2d2d44',
    marginRight: 8,
    gap: 6,
  },
  categoryChipActive: {
    backgroundColor: '#f59e0b30',
  },
  categoryChipText: {
    color: '#9ca3af',
    fontSize: 13,
    fontWeight: '500',
  },
  categoryChipTextActive: {
    color: '#f59e0b',
  },
  termsList: {
    flex: 1,
  },
  termsListContent: {
    padding: 20,
    paddingTop: 12,
  },
  termCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  termCardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  termCardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 4,
  },
  termCardShort: {
    fontSize: 14,
    color: '#9ca3af',
    lineHeight: 20,
  },
  termCategoryDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: 12,
    marginTop: 6,
  },
  termCardExpanded: {
    marginTop: 12,
  },
  termDivider: {
    height: 1,
    backgroundColor: '#2d2d44',
    marginBottom: 12,
  },
  termDetailedLabel: {
    color: '#6366f1',
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  termDetailedText: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
    marginBottom: 12,
  },
  termExampleBox: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  termExampleLabel: {
    color: '#10b981',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  termExampleText: {
    color: '#a7f3d0',
    fontSize: 13,
    lineHeight: 20,
    backgroundColor: '#10b98110',
    padding: 10,
    borderRadius: 8,
  },
  termExpandIndicator: {
    alignItems: 'center',
    marginTop: 6,
  },
  emptySearch: {
    alignItems: 'center',
    paddingTop: 60,
  },
  emptySearchText: {
    color: '#6b7280',
    fontSize: 16,
    marginTop: 12,
  },
});