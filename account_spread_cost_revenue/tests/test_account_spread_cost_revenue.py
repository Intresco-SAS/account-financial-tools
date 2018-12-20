# Copyright 2018 Onestein (<https://www.onestein.eu>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime

from psycopg2 import IntegrityError

from odoo.tools import convert_file, mute_logger
from odoo.modules.module import get_module_resource
from odoo.exceptions import ValidationError
from odoo.tests import common


class TestAccountSpreadCostRevenue(common.TransactionCase):

    def _load(self, module, *args):
        convert_file(
            self.cr,
            'account_spread_cost_revenue',
            get_module_resource(module, *args),
            {}, 'init', False, 'test', self.registry._assertion_report)

    def setUp(self):
        super().setUp()
        self._load('account', 'test', 'account_minimal_test.xml')

        def get_account(obj):
            return self.env['account.account'].search([
                ('user_type_id', '=', obj.id)
            ], limit=1)

        type_receivable = self.env.ref('account.data_account_type_receivable')
        type_expenses = self.env.ref('account.data_account_type_expenses')

        self.credit_account = get_account(type_receivable)
        self.debit_account = get_account(type_expenses)

    def test_01_account_spread_defaults(self):

        spread = self.env['account.spread'].create({
            'name': 'test',
            'invoice_type': 'out_invoice',
            'debit_account_id': self.debit_account.id,
            'credit_account_id': self.credit_account.id,
        })
        my_company = self.env.user.company_id

        self.assertTrue(spread)
        self.assertFalse(spread.line_ids)
        self.assertFalse(spread.invoice_line_ids)
        self.assertFalse(spread.invoice_line_id)
        self.assertFalse(spread.invoice_id)
        self.assertFalse(spread.account_analytic_id)
        self.assertFalse(spread.analytic_tag_ids)
        self.assertTrue(spread.move_line_auto_post)
        self.assertEqual(spread.name, 'test')
        self.assertEqual(spread.invoice_type, 'out_invoice')
        self.assertEqual(spread.company_id, my_company)
        self.assertEqual(spread.currency_id, my_company.currency_id)
        self.assertEqual(spread.period_number, 12)
        self.assertEqual(spread.period_type, 'month')
        self.assertEqual(spread.debit_account_id, self.debit_account)
        self.assertEqual(spread.credit_account_id, self.credit_account)
        self.assertEqual(spread.unspread_amount, 0.)
        self.assertEqual(spread.unposted_amount, 0.)
        self.assertEqual(spread.total_amount, 0.)
        self.assertEqual(spread.estimated_amount, 0.)
        self.assertEqual(spread.spread_date, datetime.date(2018, 1, 1))
        self.assertTrue(spread.journal_id)
        self.assertEqual(spread.journal_id.type, 'general')

    def test_02_config_defaults(self):
        my_company = self.env.user.company_id
        self.assertFalse(my_company.default_spread_revenue_account_id)
        self.assertFalse(my_company.default_spread_expense_account_id)
        self.assertFalse(my_company.default_spread_revenue_journal_id)
        self.assertFalse(my_company.default_spread_expense_journal_id)

    @mute_logger('odoo.sql_db')
    def test_03_no_defaults(self):
        with self.assertRaises(IntegrityError):
            self.env['account.spread'].create({
                'name': 'test',
            })

    @mute_logger('odoo.sql_db')
    def test_04_no_defaults(self):
        with self.assertRaises(IntegrityError):
            self.env['account.spread'].create({
                'name': 'test',
                'invoice_type': 'out_invoice',
            })

    def test_05_config_settings(self):
        my_company = self.env.user.company_id

        account_revenue = self.env['account.account'].search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_revenue').id)],
            limit=1)
        account_payable = self.env['account.account'].search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_payable').id)],
            limit=1)
        exp_journal = self.ref('account_spread_cost_revenue.expenses_journal')
        sales_journal = self.ref('account_spread_cost_revenue.sales_journal')
        my_company.default_spread_revenue_account_id = account_revenue
        my_company.default_spread_expense_account_id = account_payable
        my_company.default_spread_revenue_journal_id = sales_journal
        my_company.default_spread_expense_journal_id = exp_journal

        self.assertTrue(my_company.default_spread_revenue_account_id)
        self.assertTrue(my_company.default_spread_expense_account_id)
        self.assertTrue(my_company.default_spread_revenue_journal_id)
        self.assertTrue(my_company.default_spread_expense_journal_id)

        spread = self.env['account.spread'].new({
            'name': 'test',
        })

        self.assertTrue(spread)
        self.assertFalse(spread.line_ids)
        self.assertFalse(spread.invoice_line_ids)
        self.assertFalse(spread.invoice_line_id)
        self.assertFalse(spread.invoice_id)
        self.assertFalse(spread.account_analytic_id)
        self.assertFalse(spread.analytic_tag_ids)
        self.assertFalse(spread.move_line_auto_post)

        defaults = (self.env['account.spread'].default_get([
            'company_id',
            'currency_id',
        ]))

        self.assertEqual(defaults['company_id'], my_company.id)
        self.assertEqual(defaults['currency_id'], my_company.currency_id.id)

        spread.invoice_type = 'out_invoice'
        spread.company_id = my_company
        spread.onchange_invoice_type()
        self.assertEqual(spread.debit_account_id, account_revenue)
        self.assertFalse(spread.credit_account_id)
        self.assertEqual(spread.journal_id.id, sales_journal)
        self.assertEqual(spread.spread_type, 'sale')

        spread.invoice_type = 'in_invoice'
        spread.onchange_invoice_type()
        self.assertEqual(spread.credit_account_id, account_payable)
        self.assertEqual(spread.journal_id.id, exp_journal)
        self.assertEqual(spread.spread_type, 'purchase')

    def test_06_invoice_line_compute_spread_check(self):
        invoice_account = self.env['account.account'].search([
            ('user_type_id', '=', self.env.ref(
                'account.data_account_type_receivable').id)
        ], limit=1).id
        invoice_line_account = self.env['account.account'].search([
            ('user_type_id', '=', self.env.ref(
                'account.data_account_type_expenses').id)
        ], limit=1).id
        invoice = self.env['account.invoice'].create({
            'partner_id': self.env.ref('base.res_partner_2').id,
            'account_id': invoice_account,
            'type': 'in_invoice',
        })
        invoice_line = self.env['account.invoice.line'].create({
            'product_id': self.env.ref('product.product_product_4').id,
            'quantity': 1.0,
            'price_unit': 100.0,
            'invoice_id': invoice.id,
            'name': 'product that cost 100',
            'account_id': invoice_line_account,
        })
        invoice_line2 = invoice_line.copy()

        self.assertFalse(invoice_line.spread_id)
        self.assertEqual(invoice_line.spread_check, 'unlinked')

        spread = self.env['account.spread'].create({
            'name': 'test',
            'invoice_type': 'in_invoice',
            'debit_account_id': self.debit_account.id,
            'credit_account_id': self.credit_account.id,
        })
        invoice_line.spread_id = spread
        self.assertTrue(invoice_line.spread_id)
        self.assertEqual(invoice_line.spread_check, 'linked')
        self.assertFalse(invoice_line2.spread_id)
        self.assertEqual(invoice_line2.spread_check, 'unlinked')

        invoice.action_invoice_open()
        self.assertTrue(invoice_line.spread_id)
        self.assertEqual(invoice_line.spread_check, 'linked')
        self.assertFalse(invoice_line2.spread_id)
        self.assertEqual(invoice_line2.spread_check, 'unavailable')

    def test_07_create_spread_template(self):
        account_revenue = self.env['account.account'].search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_revenue').id)],
            limit=1)
        account_payable = self.env['account.account'].search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_payable').id)],
            limit=1)
        spread_template = self.env['account.spread.template'].create({
            'name': 'test',
            'spread_type': 'sale',
            'spread_account_id': account_revenue.id,
        })

        my_company = self.env.user.company_id
        self.assertEqual(spread_template.company_id, my_company)
        self.assertTrue(spread_template.spread_journal_id)

        exp_journal = self.ref('account_spread_cost_revenue.expenses_journal')
        sales_journal = self.ref('account_spread_cost_revenue.sales_journal')
        my_company.default_spread_revenue_account_id = account_revenue
        my_company.default_spread_expense_account_id = account_payable
        my_company.default_spread_revenue_journal_id = sales_journal
        my_company.default_spread_expense_journal_id = exp_journal

        spread_template.spread_type = 'purchase'
        spread_template.onchange_spread_type()
        self.assertTrue(spread_template.spread_journal_id)
        self.assertTrue(spread_template.spread_account_id)
        self.assertEqual(spread_template.spread_account_id, account_payable)
        self.assertEqual(spread_template.spread_journal_id.id, exp_journal)

        spread_vals = spread_template._prepare_spread_from_template()
        self.assertTrue(spread_vals['name'])
        self.assertTrue(spread_vals['template_id'])
        self.assertTrue(spread_vals['journal_id'])
        self.assertTrue(spread_vals['company_id'])
        self.assertTrue(spread_vals['invoice_type'])
        self.assertTrue(spread_vals['credit_account_id'])

        spread_template.spread_type = 'sale'
        spread_template.onchange_spread_type()
        self.assertTrue(spread_template.spread_journal_id)
        self.assertTrue(spread_template.spread_account_id)
        self.assertEqual(spread_template.spread_account_id, account_revenue)
        self.assertEqual(spread_template.spread_journal_id.id, sales_journal)

        spread_vals = spread_template._prepare_spread_from_template()
        self.assertTrue(spread_vals['name'])
        self.assertTrue(spread_vals['template_id'])
        self.assertTrue(spread_vals['journal_id'])
        self.assertTrue(spread_vals['company_id'])
        self.assertTrue(spread_vals['invoice_type'])
        self.assertTrue(spread_vals['debit_account_id'])

    def test_08_check_template_invoice_type(self):
        account_revenue = self.env['account.account'].search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_revenue').id)],
            limit=1)
        account_payable = self.env['account.account'].search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_payable').id)],
            limit=1)
        template_sale = self.env['account.spread.template'].create({
            'name': 'test',
            'spread_type': 'sale',
            'spread_account_id': account_revenue.id,
        })
        template_purchase = self.env['account.spread.template'].create({
            'name': 'test',
            'spread_type': 'purchase',
            'spread_account_id': account_payable.id,
        })
        spread = self.env['account.spread'].create({
            'name': 'test',
            'invoice_type': 'out_invoice',
            'debit_account_id': self.debit_account.id,
            'credit_account_id': self.credit_account.id,
        })
        spread.template_id = template_sale
        self.assertEqual(spread.template_id, template_sale)
        with self.assertRaises(ValidationError):
            spread.template_id = template_purchase
        self.assertEqual(spread.invoice_type, 'out_invoice')
        spread.onchange_template()
        self.assertEqual(spread.invoice_type, 'in_invoice')

        spread.template_id = False
        spread.invoice_type = 'in_invoice'
        spread.template_id = template_purchase
        self.assertEqual(spread.template_id, template_purchase)
        with self.assertRaises(ValidationError):
            spread.template_id = template_sale
        self.assertEqual(spread.invoice_type, 'in_invoice')
        spread.onchange_template()
        self.assertEqual(spread.invoice_type, 'out_invoice')

        spread.template_id = False
        spread.invoice_type = 'out_invoice'
        spread.template_id = template_sale
        self.assertEqual(spread.template_id, template_sale)
        with self.assertRaises(ValidationError):
            spread.invoice_type = 'in_invoice'
        self.assertEqual(spread.invoice_type, 'in_invoice')
        spread.onchange_template()
        self.assertEqual(spread.invoice_type, 'out_invoice')

        spread.template_id = False
        spread.invoice_type = 'in_invoice'
        spread.template_id = template_purchase
        self.assertEqual(spread.template_id, template_purchase)
        with self.assertRaises(ValidationError):
            spread.invoice_type = 'out_invoice'
        self.assertEqual(spread.invoice_type, 'out_invoice')
        spread.onchange_template()
        self.assertEqual(spread.invoice_type, 'in_invoice')

    def test_09_wrong_invoice_type(self):
        invoice_account = self.env['account.account'].search([
            ('user_type_id', '=', self.env.ref(
                'account.data_account_type_receivable').id)
        ], limit=1).id
        invoice_line_account = self.env['account.account'].search([
            ('user_type_id', '=', self.env.ref(
                'account.data_account_type_expenses').id)
        ], limit=1).id
        invoice = self.env['account.invoice'].create({
            'partner_id': self.env.ref('base.res_partner_2').id,
            'account_id': invoice_account,
            'type': 'in_invoice',
        })
        invoice_line = self.env['account.invoice.line'].create({
            'product_id': self.env.ref('product.product_product_4').id,
            'quantity': 1.0,
            'price_unit': 100.0,
            'invoice_id': invoice.id,
            'name': 'product that cost 100',
            'account_id': invoice_line_account,
        })
        spread = self.env['account.spread'].create({
            'name': 'test',
            'invoice_type': 'out_invoice',
            'debit_account_id': self.debit_account.id,
            'credit_account_id': self.credit_account.id,
        })
        with self.assertRaises(ValidationError):
            invoice_line.spread_id = spread
